import logging
import sys
import os
import time
import jwt 
from fastapi import FastAPI, Request, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware # <--- NEW: For Browser Access
from pydantic import BaseModel
from web3 import Web3  
from web3.exceptions import TransactionNotFound
from eth_account import Account
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException

# ==========================================
#              CONFIGURATION
# ==========================================

PORT = int(os.getenv("PORT"))
RPC_URL = os.getenv("RPC_URL")
OWNER_PRIVATE_KEY = os.getenv("OWNER_PRIVATE_KEY")
JWT_SECRET = os.getenv("JWT_SECRET")
SYSCALL_CONTRACT_ADDRESS = os.getenv("SYSCALL_CONTRACT_ADDRESS")

# SMS Config
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_FROM_NUMBER = os.getenv("TWILIO_FROM_NUMBER")

# --- ABIs ---
# Only the main contract ABI is needed now
CONTRACT_ABI = '[{"anonymous":false,"inputs":[{"indexed":true,"internalType":"uint256","name":"paymentId","type":"uint256"},{"indexed":true,"internalType":"address","name":"user","type":"address"},{"indexed":false,"internalType":"string","name":"name","type":"string"},{"indexed":false,"internalType":"uint256","name":"amount","type":"uint256"},{"indexed":false,"internalType":"uint256","name":"quantity","type":"uint256"},{"indexed":false,"internalType":"uint256","name":"timestamp","type":"uint256"}],"name":"ActionPaid","type":"event"}, {"inputs":[{"internalType":"uint256","name":"","type":"uint256"}],"name":"isConsumed","outputs":[{"internalType":"bool","name":"","type":"bool"}],"stateMutability":"view","type":"function"}, {"inputs":[{"internalType":"uint256","name":"paymentId","type":"uint256"}],"name":"consumePayment","outputs":[],"stateMutability":"nonpayable","type":"function"}]'

# --- Logger ---
if not os.path.exists("logs"): os.makedirs("logs")
logger = logging.getLogger("syscall-relayer")
logger.setLevel(logging.DEBUG) 
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setFormatter(formatter)
logger.addHandler(stream_handler)

app = FastAPI(title="Syscall Relayer (Centralized Config)", version="1.1.0")

# --- CORS MIDDLEWARE (Mode SDK Public Universel) ---
app.add_middleware(
    CORSMiddleware,
    # Au lieu de "*", on utilise une REGEX qui dit "tout ce qui commence par http ou https"
    # FastAPI va renvoyer l'origine exacte du client dans le header, ce qui satisfait le navigateur.
    allow_origin_regex="https?://.*", 
    
    # Cela permet au JWT et aux headers d'autorisation de passer
    allow_credentials=True,
    
    # On autorise toutes les méthodes (POST, GET, OPTIONS...)
    allow_methods=["*"],
    
    # On autorise tous les headers (notamment "Authorization" pour le Bearer token)
    allow_headers=["*"],
)

# --- Models ---
class VerificationPayload(BaseModel):
    tx_hash: str        
    signature: str      
    sender: str         

class DispatchPayload(BaseModel):
    destination: str 
    content: str      

# ==========================================
#           CORE LOGIC (GATEWAY)
# ==========================================

def execute_sms_delivery(destination: str, content: str):
    logger.info(f"   >>> Gateway: Processing SMS to {destination}")

    if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN:
        logger.error("   !!! Twilio credentials missing in .env")
        raise Exception("Twilio credentials missing")

    try:
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        message = client.messages.create(
            body=content,
            from_=TWILIO_FROM_NUMBER,
            to=destination
        )
        logger.info(f"   >>> Twilio Sent: SID {message.sid}")
        return message.sid
    except TwilioRestException as e:
        logger.error(f"   !!! Twilio Error: {e}")
        raise e

# ==========================================
#        BLOCKCHAIN LOGIC (RELAYER)
# ==========================================

def verify_payment_on_chain(tx_hash: str):
    try:
        w3 = Web3(Web3.HTTPProvider(RPC_URL))
        if not w3.is_connected(): return None

        try:
            tx_receipt = w3.eth.get_transaction_receipt(tx_hash)
        except TransactionNotFound: return None

        if tx_receipt['status'] != 1: return None

        # DIRECT ADDRESS USAGE
        if not SYSCALL_CONTRACT_ADDRESS:
            logger.critical("SYSCALL_CONTRACT_ADDRESS not set in environment")
            return None

        contract = w3.eth.contract(address=SYSCALL_CONTRACT_ADDRESS, abi=CONTRACT_ABI)
        
        action_paid_events = contract.events.ActionPaid().process_receipt(tx_receipt)
        if not action_paid_events: return None
            
        event_args = action_paid_events[0]['args']
        payment_id = event_args['paymentId']
        quantity = event_args.get('quantity', 0)

        if contract.functions.isConsumed(payment_id).call():
            logger.warning(f"Replay Attempt: Payment {payment_id} already consumed.")
            return None

        logger.info(f"Payment Validated: ID {payment_id} | Service: {event_args['name']} | Cap: {quantity}")
        
        return {
            "paymentId": payment_id,
            "service": event_args['name'],
            "user": event_args['user'],
            "quantity": quantity 
        }
    except Exception as e:
        logger.error(f"Web3 Verification Error: {str(e)}")
        return None

def mark_consumed_on_chain(payment_id: int):
    if not OWNER_PRIVATE_KEY:
        logger.error("Owner Private Key not found.")
        return None

    try:
        w3 = Web3(Web3.HTTPProvider(RPC_URL))
        account = Account.from_key(OWNER_PRIVATE_KEY)
        
        # DIRECT ADDRESS USAGE
        contract = w3.eth.contract(address=SYSCALL_CONTRACT_ADDRESS, abi=CONTRACT_ABI)

        contract_function = contract.functions.consumePayment(payment_id)
        
        nonce = w3.eth.get_transaction_count(account.address, 'pending')
        current_gas_price = w3.eth.gas_price

        try:
            estimated_gas = contract_function.estimate_gas({
                'from': account.address, 
                'nonce': nonce,
                'value': 0
            })
            gas_limit = int(estimated_gas * 1.2)
        except Exception as e:
            logger.warning(f"Gas estimation failed, using fallback: {e}")
            gas_limit = 300000 

        tx_params = {
            'from': account.address,
            'nonce': nonce,
            'gas': gas_limit,
            'gasPrice': current_gas_price,
            'chainId': w3.eth.chain_id
        }
        
        tx = contract_function.build_transaction(tx_params)
        signed_tx = w3.eth.account.sign_transaction(tx, OWNER_PRIVATE_KEY)
        
        tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
        
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
        
        if receipt.status == 1:
            cost_eth = w3.from_wei(receipt.gasUsed * current_gas_price, 'ether')
            logger.info(f"On-Chain Consumption Success: TX {tx_hash.hex()} | Cost: {cost_eth:.6f} ETH")
            return tx_hash.hex()
        else:
            logger.error("On-Chain Consumption Failed (Reverted)")
            return None

    except Exception as e:
        logger.error(f"Blockchain Write Error: {e}")
        return None

# ==========================================
#                ENDPOINTS
# ==========================================

# --- NEW: BOOTSTRAP ENDPOINT ---
@app.get("/config")
def get_configuration():
    """ 
    Delivers the blockchain configuration to the SDK.
    The SDK calls this first to know where to connect.
    """
    if not SYSCALL_CONTRACT_ADDRESS:
        raise HTTPException(status_code=500, detail="Relayer not configured properly")
        
    return {
        "rpc_url": RPC_URL,
        "contract_address": SYSCALL_CONTRACT_ADDRESS
    }

@app.get("/health")
def health_check():
    return {"status": "ok", "mode": "centralized-config"}

@app.post("/verify")
async def verify_transaction(payload: VerificationPayload, request: Request):
    logger.info(f"[Step 4] Verification Request: {payload.tx_hash}")
    
    payment_data = verify_payment_on_chain(payload.tx_hash)
    if not payment_data:
        raise HTTPException(status_code=400, detail="Invalid Payment or Already Consumed")

    token_payload = {
        "iss": "syscall-relayer",
        "sub": payment_data["user"],
        "pid": payment_data["paymentId"],
        "svc": payment_data["service"],
        "qty": payment_data["quantity"],
        "iat": int(time.time()),
        "exp": int(time.time()) + 300
    }
    
    token = jwt.encode(token_payload, JWT_SECRET, algorithm="HS256")
    logger.info(f"[Step 6] JWT Issued for Payment {payment_data['paymentId']}")

    return {"status": "authorized", "jwt": token}

@app.post("/dispatch")
async def dispatch_action(payload: DispatchPayload, authorization: str = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer Token")

    token = authorization.split(" ")[1]

    try:
        decoded = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        payment_id = decoded.get("pid")
        service_type = decoded.get("svc")
        allowed_quantity = decoded.get("qty", 0)
        
        content_length = len(payload.content.encode('utf-8'))
        if content_length > allowed_quantity:
            logger.warning(f"Fraud Attempt: Paid for {allowed_quantity}, sent {content_length}")
            raise HTTPException(status_code=402, detail=f"Content too long. Paid for {allowed_quantity} bytes.")

        logger.info(f"[Step 7] Dispatching {service_type.upper()} for Payment ID {payment_id}")

        provider_sid = "unknown"
        if service_type == "sms":
            try:
                provider_sid = execute_sms_delivery(payload.destination, payload.content)
            except Exception as e:
                raise HTTPException(status_code=502, detail=f"SMS Provider Error: {str(e)}")
        
        logger.info(f"   >>> Marking Payment {payment_id} as consumed on-chain...")
        consume_tx = mark_consumed_on_chain(payment_id)
        
        if not consume_tx:
            logger.critical("   !!! CRITICAL: Service delivered but failed to mark on-chain.")

        logger.info(f"[Step 9] Returning ACK to SDK")
        
        return {
            "status": "success",
            "service": service_type,
            "destination": payload.destination,
            "meta": {
                "paymentId": payment_id,
                "consumptionTx": consume_tx, 
                "providerSid": provider_sid,
                "timestamp": int(time.time())
            }
        }

    except jwt.ExpiredSignatureError: raise HTTPException(status_code=401, detail="Token Expired")
    except jwt.InvalidTokenError: raise HTTPException(status_code=401, detail="Invalid Token")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
