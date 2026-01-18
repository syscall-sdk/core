import logging
import sys
import os
import time
from fastapi import FastAPI, Request, HTTPException, Header, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
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

PORT = int(os.getenv("SYSCALL-SMS-RELAYER-PORT", 8080))
RPC_URL = os.getenv("SYSCALL-SMS-RELAYER-RPC_URL")
OWNER_PRIVATE_KEY = os.getenv("SYSCALL-SMS-RELAYER-OWNER_PRIVATE_KEY")
SYSCALL_CONTRACT_ADDRESS = os.getenv("SYSCALL-SMS-RELAYER-SYSCALL_CONTRACT_ADDRESS")

# [STRICT] Chain Configuration
CHAIN_ID_ENV = os.getenv("SYSCALL-SMS-RELAYER-CHAIN_ID")
if not CHAIN_ID_ENV:
    raise ValueError("CRITICAL ERROR: 'SYSCALL-SMS-RELAYER-CHAIN_ID' environment variable is missing.")
CHAIN_ID = int(CHAIN_ID_ENV)

# Gateways Config
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

app = FastAPI(title="Syscall Relayer (SMS Secure)", version="2.9.0")

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex="https?://.*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if not os.path.exists("static"): os.makedirs("static")
app.mount("/static", StaticFiles(directory="static"), name="static")

class DispatchPayload(BaseModel):
    tx_hash: str
    secret: str         
    destination: str
    content: str
    subject: str = "SMS"     
    sender_name: str = "SDK" 

# ==========================================
#      SECURITY: ANTI-REPLAY CACHE
# ==========================================
# [SECURITY] Memory set to track transactions currently being processed.
# Prevents race conditions where a user sends the same TX multiple times
# before the "consumePayment" transaction is mined on-chain.
PROCESSING_CACHE = set()

# ==========================================
#          GLOBAL CONNECTIONS (SPEED)
# ==========================================
# [OPTIMIZATION] Global Web3 initialization to reuse TCP/SSL connections.
# This removes the 1-2s handshake latency per request.
try:
    w3_global = Web3(Web3.HTTPProvider(RPC_URL))
    if w3_global.is_connected():
        logger.info(f"✅ Connected to RPC: {RPC_URL}")
    else:
        logger.warning(f"⚠️ Failed to connect to RPC: {RPC_URL}")
except Exception as e:
    logger.error(f"❌ RPC Connection Error: {e}")
    w3_global = None

# ==========================================
#           CORE LOGIC (GATEWAY)
# ==========================================

def execute_sms_delivery(destination: str, content: str):
    logger.info(f"   >>> Gateway: Sending SMS to {destination} (Background)...")
    if not TWILIO_ACCOUNT_SID: 
        logger.error("Twilio Config Missing")
        return

    try:
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        msg = client.messages.create(body=content, from_=TWILIO_FROM_NUMBER, to=destination)
        logger.info(f"   >>> Gateway: SMS Sent Successfully via Twilio (SID: {msg.sid})")
        return msg.sid
    except Exception as e:
        logger.error(f"   !!! Twilio Error: {e}")

# ==========================================
#        BLOCKCHAIN LOGIC (VERIFIER)
# ==========================================

def verify_and_consume(tx_hash: str, secret: str):
    if not w3_global: return None # Fail fast if no RPC

    try:
        try:
            tx_receipt = w3_global.eth.get_transaction_receipt(tx_hash)
        except TransactionNotFound: return None

        if tx_receipt['status'] != 1: return None

        checksum_address = Web3.to_checksum_address(SYSCALL_CONTRACT_ADDRESS)
        contract = w3_global.eth.contract(address=checksum_address, abi=CONTRACT_ABI)
        
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
    if not OWNER_PRIVATE_KEY or not w3_global: return None
    try:
        account = Account.from_key(OWNER_PRIVATE_KEY)
        
        checksum_address = Web3.to_checksum_address(SYSCALL_CONTRACT_ADDRESS)
        contract = w3_global.eth.contract(address=checksum_address, abi=CONTRACT_ABI)
        
        func = contract.functions.consumePayment(payment_id)
        
        tx_params = {
            'from': account.address,
            'nonce': w3_global.eth.get_transaction_count(account.address, 'pending'),
            'gas': 300000,
            'gasPrice': w3_global.eth.gas_price,
            'chainId': w3_global.eth.chain_id
        }
        
        signed = w3_global.eth.account.sign_transaction(func.build_transaction(tx_params), OWNER_PRIVATE_KEY)
        tx_hash = w3_global.eth.send_raw_transaction(signed.raw_transaction)
        
        logger.info(f"   >>> Chain Write Sent: {tx_hash.hex()}")
        return tx_hash.hex()
    except Exception as e:
        logger.error(f"Chain Write Error: {e}")
        return None

# ==========================================
#                ENDPOINTS
# ==========================================

@app.get("/")
async def serve_frontend():
    return FileResponse("static/index.html")

@app.get("/config")
def get_config():
    safe_addr = Web3.to_checksum_address(SYSCALL_CONTRACT_ADDRESS) if SYSCALL_CONTRACT_ADDRESS else None
    return {
        "rpc_url": RPC_URL, 
        "contract_address": safe_addr,
        "chain_id": CHAIN_ID 
    }

@app.post("/dispatch")
async def dispatch_action(payload: DispatchPayload, background_tasks: BackgroundTasks):
    logger.info(f"Received Dispatch Request for TX: {payload.tx_hash}")

    # [SECURITY] 1. Check Memory Cache (Fastest)
    if payload.tx_hash in PROCESSING_CACHE:
        logger.warning(f"⛔ REPLAY BLOCKED: TX {payload.tx_hash} is already processing.")
        raise HTTPException(status_code=409, detail="Transaction already processing")

    # [SECURITY] 2. Lock Transaction in Memory
    PROCESSING_CACHE.add(payload.tx_hash)

    try:
        # 3. Verify on Chain (Fast via Global RPC)
        valid_payment = verify_and_consume(payload.tx_hash, payload.secret)
        
        if not valid_payment:
            # Unlock if invalid
            PROCESSING_CACHE.discard(payload.tx_hash) 
            raise HTTPException(status_code=400, detail="Invalid Payment, Bad Secret, or Replay")

        payment_id = valid_payment['paymentId']
        service_type = valid_payment['service']
        allowed_qty = valid_payment['quantity']

        content_len = len(payload.content.encode('utf-8'))
        if content_len > allowed_qty:
            PROCESSING_CACHE.discard(payload.tx_hash)
            raise HTTPException(status_code=402, detail=f"Content too long. Paid for {allowed_qty}")

        provider_sid = "unknown"
        try:
            if service_type == "sms":
                # 4. Async Delivery
                background_tasks.add_task(
                    execute_sms_delivery,
                    payload.destination, 
                    payload.content
                )
                provider_sid = "queued" 
            else:
                PROCESSING_CACHE.discard(payload.tx_hash)
                raise HTTPException(status_code=400, detail="Unknown Service (Email Disabled)")
        except Exception as e:
             PROCESSING_CACHE.discard(payload.tx_hash)
             raise HTTPException(status_code=502, detail=str(e))

        # 5. Chain Update (Fast via Global RPC)
        tx = mark_consumed_on_chain(payment_id)
        
        # Note: We intentionally DO NOT remove the hash from PROCESSING_CACHE here.
        # It stays locked in memory until the server restarts or the pod is killed.
        # This covers the "mining time" window effectively.
        
        return {
            "status": "success",
            "service": service_type,
            "meta": {
                "paymentId": payment_id,
                "consumptionTx": tx,
                "providerSid": provider_sid
            }
        }
    except Exception as e:
        # Safety Unlock in case of unexpected crash
        PROCESSING_CACHE.discard(payload.tx_hash)
        raise e

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
