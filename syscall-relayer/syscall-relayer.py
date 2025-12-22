import logging
import sys
import os
import time
import jwt 
from fastapi import FastAPI, Request, HTTPException, Header
from pydantic import BaseModel
from web3 import Web3  
from web3.exceptions import TransactionNotFound
from eth_account import Account
# Twilio Import
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException

# ==========================================
#              CONFIGURATION
# ==========================================

PORT = int(os.getenv("PORT"))
RPC_URL = os.getenv("RPC_URL")
OWNER_PRIVATE_KEY = os.getenv("OWNER_PRIVATE_KEY")
PROXY_ADDRESS = os.getenv("PROXY_ADDRESS")
JWT_SECRET = os.getenv("JWT_SECRET")

# --- SMS Configuration (Direct Twilio) ---
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_FROM_NUMBER = os.getenv("TWILIO_FROM_NUMBER")

# --- ABIs ---
PROXY_ABI = '[{"inputs":[],"name":"syscallContract","outputs":[{"internalType":"address","name":"","type":"address"}],"stateMutability":"view","type":"function"}]'
CONTRACT_ABI = '[{"anonymous":false,"inputs":[{"indexed":true,"internalType":"uint256","name":"paymentId","type":"uint256"},{"indexed":true,"internalType":"address","name":"user","type":"address"},{"indexed":false,"internalType":"string","name":"name","type":"string"},{"indexed":false,"internalType":"uint256","name":"amount","type":"uint256"},{"indexed":false,"internalType":"uint256","name":"quantity","type":"uint256"},{"indexed":false,"internalType":"uint256","name":"timestamp","type":"uint256"}],"name":"ActionPaid","type":"event"}, {"inputs":[{"internalType":"uint256","name":"","type":"uint256"}],"name":"isConsumed","outputs":[{"internalType":"bool","name":"","type":"bool"}],"stateMutability":"view","type":"function"}, {"inputs":[{"internalType":"uint256","name":"paymentId","type":"uint256"}],"name":"consumePayment","outputs":[],"stateMutability":"nonpayable","type":"function"}]'

# --- Logger ---
if not os.path.exists("logs"): os.makedirs("logs")
logger = logging.getLogger("syscall-relayer")
logger.setLevel(logging.DEBUG) 
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setFormatter(formatter)
logger.addHandler(stream_handler)

app = FastAPI(title="Syscall Relayer (Production Ready)", version="1.0.0")

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
    """
    Sends the SMS via Twilio using the credentials loaded in ENV.
    """
    logger.info(f"   >>> Gateway: Processing SMS to {destination}")

    # Fail fast if config is missing
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
        # We re-raise the exception so the main loop knows it failed
        raise e

# ==========================================
#        BLOCKCHAIN LOGIC (RELAYER)
# ==========================================

def get_authoritative_contract(w3: Web3) -> str:
    try:
        proxy = w3.eth.contract(address=PROXY_ADDRESS, abi=PROXY_ABI)
        return proxy.functions.syscallContract().call()
    except Exception as e:
        logger.critical(f"Proxy Error: {e}")
        return None

def verify_payment_on_chain(tx_hash: str):
    try:
        w3 = Web3(Web3.HTTPProvider(RPC_URL))
        if not w3.is_connected(): return None

        try:
            tx_receipt = w3.eth.get_transaction_receipt(tx_hash)
        except TransactionNotFound: return None

        if tx_receipt['status'] != 1: return None

        target_contract = get_authoritative_contract(w3)
        contract = w3.eth.contract(address=target_contract, abi=CONTRACT_ABI)
        
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
    """ Writes to blockchain with Auto-Gas and 'Pending' nonce support. """
    if not OWNER_PRIVATE_KEY:
        logger.error("Owner Private Key not found.")
        return None

    try:
        w3 = Web3(Web3.HTTPProvider(RPC_URL))
        account = Account.from_key(OWNER_PRIVATE_KEY)
        target_contract = get_authoritative_contract(w3)
        contract = w3.eth.contract(address=target_contract, abi=CONTRACT_ABI)

        contract_function = contract.functions.consumePayment(payment_id)
        
        # 'pending' nonce handles basic concurrency without DB
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
        tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)
        
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

        # --- A. ACTION EXECUTION (Twilio) ---
        provider_sid = "unknown"
        
        if service_type == "sms":
            try:
                # Si les credentials de Test sont dans le .env, Twilio ne facturera pas
                # et renverra un SID de test.
                provider_sid = execute_sms_delivery(payload.destination, payload.content)
            except Exception as e:
                # IMPORTANT: On arrête ici. On ne marque PAS "consommé" sur la blockchain.
                # L'utilisateur pourra réessayer (ou un mécanisme de retry auto s'activera).
                raise HTTPException(status_code=502, detail=f"SMS Provider Error: {str(e)}")
        
        elif service_type == "email":
            # Future implementation
            pass

        # --- B. BLOCKCHAIN CONSUMPTION ---
        logger.info(f"   >>> Marking Payment {payment_id} as consumed on-chain...")
        consume_tx = mark_consumed_on_chain(payment_id)
        
        if not consume_tx:
            # État critique : SMS envoyé, mais Blockchain a échoué.
            logger.critical("   !!! CRITICAL: Service delivered but failed to mark on-chain.")
            # Ici, idéalement, on devrait alerter l'admin.

        # --- C. ACKNOWLEDGMENT ---
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
