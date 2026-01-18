import logging
import sys
import os
import time
from fastapi import FastAPI, Request, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles  # [NEW]
from fastapi.responses import FileResponse   # [NEW]
from pydantic import BaseModel
from web3 import Web3
from web3.exceptions import TransactionNotFound
from eth_account import Account
from eth_utils import keccak
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException

# ==========================================
#              CONFIGURATION
# ==========================================

PORT = int(os.getenv("SYSCALL-SMS-RELAYER-PORT", 8000))
RPC_URL = os.getenv("SYSCALL-SMS-RELAYER-RPC_URL")
OWNER_PRIVATE_KEY = os.getenv("SYSCALL-SMS-RELAYER-OWNER_PRIVATE_KEY")
SYSCALL_CONTRACT_ADDRESS = os.getenv("SYSCALL-SMS-RELAYER-SYSCALL_CONTRACT_ADDRESS")

# Gateways Config (SMS Specific)
TWILIO_ACCOUNT_SID = os.getenv("SYSCALL-SMS-RELAYER-TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("SYSCALL-SMS-RELAYER-TWILIO_AUTH_TOKEN")
TWILIO_FROM_NUMBER = os.getenv("SYSCALL-SMS-RELAYER-TWILIO_FROM_NUMBER")

CONTRACT_ABI = '[{"anonymous":false,"inputs":[{"indexed":true,"internalType":"uint256","name":"paymentId","type":"uint256"},{"indexed":true,"internalType":"address","name":"user","type":"address"},{"indexed":false,"internalType":"string","name":"name","type":"string"},{"indexed":false,"internalType":"uint256","name":"amount","type":"uint256"},{"indexed":false,"internalType":"uint256","name":"quantity","type":"uint256"},{"indexed":false,"internalType":"bytes32","name":"commitment","type":"bytes32"},{"indexed":false,"internalType":"uint256","name":"timestamp","type":"uint256"}],"name":"ActionPaid","type":"event"}, {"inputs":[{"internalType":"uint256","name":"","type":"uint256"}],"name":"isConsumed","outputs":[{"internalType":"bool","name":"","type":"bool"}],"stateMutability":"view","type":"function"}, {"inputs":[{"internalType":"uint256","name":"paymentId","type":"uint256"}],"name":"consumePayment","outputs":[],"stateMutability":"nonpayable","type":"function"}]'

# --- Logger ---
if not os.path.exists("logs"): os.makedirs("logs")
logger = logging.getLogger("syscall-relayer")
logger.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setFormatter(formatter)
logger.addHandler(stream_handler)

app = FastAPI(title="Syscall Relayer (SMS Only)", version="2.3.0")

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex="https?://.*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# [NEW] STATIC FILES CONFIGURATION
# Ensure 'static' directory exists inside container
if not os.path.exists("static"):
    os.makedirs("static")

# Mount the static directory to serve CSS/JS/Images at /static path
app.mount("/static", StaticFiles(directory="static"), name="static")

# --- Models ---
class DispatchPayload(BaseModel):
    tx_hash: str
    secret: str         
    destination: str
    content: str
    subject: str = "SMS"     
    sender_name: str = "SDK" 

# ==========================================
#           CORE LOGIC (GATEWAY)
# ==========================================

def execute_sms_delivery(destination: str, content: str):
    logger.info(f"   >>> Gateway: SMS to {destination}")
    if not TWILIO_ACCOUNT_SID: raise Exception("Twilio config missing")
    try:
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        msg = client.messages.create(body=content, from_=TWILIO_FROM_NUMBER, to=destination)
        return msg.sid
    except Exception as e:
        logger.error(f"   !!! Twilio Error: {e}")
        raise e

# ==========================================
#        BLOCKCHAIN LOGIC (VERIFIER)
# ==========================================

def verify_and_consume(tx_hash: str, secret: str):
    try:
        w3 = Web3(Web3.HTTPProvider(RPC_URL))
        if not w3.is_connected(): raise Exception("RPC Connection Failed")

        try:
            tx_receipt = w3.eth.get_transaction_receipt(tx_hash)
        except TransactionNotFound: return None

        if tx_receipt['status'] != 1: return None

        checksum_address = Web3.to_checksum_address(SYSCALL_CONTRACT_ADDRESS)
        contract = w3.eth.contract(address=checksum_address, abi=CONTRACT_ABI)
        
        events = contract.events.ActionPaid().process_receipt(tx_receipt)
        if not events: return None
        
        args = events[0]['args']
        payment_id = args['paymentId']
        service = args['name']
        quantity = args['quantity']
        on_chain_commitment = args['commitment']

        secret_bytes = bytes.fromhex(secret.replace("0x", ""))
        computed_hash = keccak(secret_bytes)

        if computed_hash != on_chain_commitment:
            logger.warning(f"SECURITY ALERT: Hash Mismatch! ID: {payment_id}")
            return None

        if contract.functions.isConsumed(payment_id).call():
            logger.warning(f"Replay Attempt: Payment {payment_id} already consumed.")
            return None

        return {
            "paymentId": payment_id,
            "service": service,
            "quantity": quantity
        }

    except Exception as e:
        logger.error(f"Verification Error: {str(e)}")
        return None

def mark_consumed_on_chain(payment_id: int):
    if not OWNER_PRIVATE_KEY: return None
    try:
        w3 = Web3(Web3.HTTPProvider(RPC_URL))
        account = Account.from_key(OWNER_PRIVATE_KEY)
        
        checksum_address = Web3.to_checksum_address(SYSCALL_CONTRACT_ADDRESS)
        contract = w3.eth.contract(address=checksum_address, abi=CONTRACT_ABI)
        
        func = contract.functions.consumePayment(payment_id)
        
        tx_params = {
            'from': account.address,
            'nonce': w3.eth.get_transaction_count(account.address, 'pending'),
            'gas': 300000,
            'gasPrice': w3.eth.gas_price,
            'chainId': w3.eth.chain_id
        }
        
        signed = w3.eth.account.sign_transaction(func.build_transaction(tx_params), OWNER_PRIVATE_KEY)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        w3.eth.wait_for_transaction_receipt(tx_hash)
        return tx_hash.hex()
    except Exception as e:
        logger.error(f"Chain Write Error: {e}")
        return None

# ==========================================
#                ENDPOINTS
# ==========================================

# [NEW] SERVE INDEX.HTML AT ROOT
@app.get("/")
async def serve_frontend():
    return FileResponse("static/index.html")

@app.get("/config")
def get_config():
    safe_addr = Web3.to_checksum_address(SYSCALL_CONTRACT_ADDRESS) if SYSCALL_CONTRACT_ADDRESS else None
    return {"rpc_url": RPC_URL, "contract_address": safe_addr}

@app.post("/dispatch")
async def dispatch_action(payload: DispatchPayload):
    logger.info(f"Received Dispatch Request for TX: {payload.tx_hash}")

    valid_payment = verify_and_consume(payload.tx_hash, payload.secret)
    
    if not valid_payment:
        raise HTTPException(status_code=400, detail="Invalid Payment, Bad Secret, or Replay")

    payment_id = valid_payment['paymentId']
    service_type = valid_payment['service']
    allowed_qty = valid_payment['quantity']

    content_len = len(payload.content.encode('utf-8'))
    if content_len > allowed_qty:
        raise HTTPException(status_code=402, detail=f"Content too long. Paid for {allowed_qty}")

    provider_sid = "unknown"
    try:
        if service_type == "sms":
            provider_sid = execute_sms_delivery(payload.destination, payload.content)
        else:
            raise HTTPException(status_code=400, detail="Unknown Service")
    except Exception as e:
         raise HTTPException(status_code=502, detail=str(e))

    tx = mark_consumed_on_chain(payment_id)
    
    return {
        "status": "success",
        "service": service_type,
        "meta": {
            "paymentId": payment_id,
            "consumptionTx": tx,
            "providerSid": provider_sid
        }
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
