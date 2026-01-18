import logging
import sys
import os
import smtplib
import ssl
from email.utils import make_msgid, formatdate, formataddr
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from fastapi import FastAPI, Request, HTTPException, Header, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from web3 import Web3
from web3.exceptions import TransactionNotFound
from eth_account import Account
from eth_utils import keccak

# ==========================================
#              CONFIGURATION
# ==========================================

PORT = int(os.getenv("SYSCALL-EMAIL-RELAYER-PORT"))
RPC_URL = os.getenv("SYSCALL-EMAIL-RELAYER-RPC_URL")
OWNER_PRIVATE_KEY = os.getenv("SYSCALL-EMAIL-RELAYER-OWNER_PRIVATE_KEY")
SYSCALL_CONTRACT_ADDRESS = os.getenv("SYSCALL-EMAIL-RELAYER-SYSCALL_CONTRACT_ADDRESS")

# Chain Configuration
CHAIN_ID = int(os.getenv("SYSCALL-EMAIL-RELAYER-CHAIN_ID"))

# EMAIL Config
SMTP_HOST = os.getenv("SYSCALL-EMAIL-RELAYER-SMTP_HOST") 
SMTP_PORT = int(os.getenv("SYSCALL-EMAIL-RELAYER-SMTP_PORT"))
SMTP_USER = os.getenv("SYSCALL-EMAIL-RELAYER-SMTP_USER")                 
SMTP_PASSWORD = os.getenv("SYSCALL-EMAIL-RELAYER-SMTP_PASSWORD")
SMTP_FROM_EMAIL = os.getenv("SYSCALL-EMAIL-RELAYER-SMTP_FROM_EMAIL")

CONTRACT_ABI = '[{"anonymous":false,"inputs":[{"indexed":true,"internalType":"uint256","name":"paymentId","type":"uint256"},{"indexed":true,"internalType":"address","name":"user","type":"address"},{"indexed":false,"internalType":"string","name":"name","type":"string"},{"indexed":false,"internalType":"uint256","name":"amount","type":"uint256"},{"indexed":false,"internalType":"uint256","name":"quantity","type":"uint256"},{"indexed":false,"internalType":"bytes32","name":"commitment","type":"bytes32"},{"indexed":false,"internalType":"uint256","name":"timestamp","type":"uint256"}],"name":"ActionPaid","type":"event"}, {"inputs":[{"internalType":"uint256","name":"","type":"uint256"}],"name":"isConsumed","outputs":[{"internalType":"bool","name":"","type":"bool"}],"stateMutability":"view","type":"function"}, {"inputs":[{"internalType":"uint256","name":"paymentId","type":"uint256"}],"name":"consumePayment","outputs":[],"stateMutability":"nonpayable","type":"function"}]'

# --- Logger ---
if not os.path.exists("logs"): os.makedirs("logs")
logger = logging.getLogger("syscall-relayer")
logger.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setFormatter(formatter)
logger.addHandler(stream_handler)

app = FastAPI(title="Syscall Relayer (Email Secure)", version="2.9.0")

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
    subject: str = "Syscall Notification"
    sender_name: str = "Syscall Oracle"

# ==========================================
#      SECURITY: ANTI-REPLAY CACHE
# ==========================================
# [SECURITY] Anti-replay memory lock
PROCESSING_CACHE = set()

# ==========================================
#          GLOBAL CONNECTIONS (SPEED)
# ==========================================
# [OPTIMIZATION] Global RPC Connection
try:
    w3_global = Web3(Web3.HTTPProvider(RPC_URL))
    if w3_global.is_connected():
        logger.info(f"✅ Connected to RPC: {RPC_URL}")
    else:
        logger.warning(f"⚠️ Failed to connect to RPC")
except Exception as e:
    logger.error(f"❌ RPC Connection Error: {e}")
    w3_global = None

# ==========================================
#           CORE LOGIC (GATEWAY)
# ==========================================

def execute_email_delivery(destination: str, subject: str, sender_name: str, content: str):
    logger.info(f"   >>> Gateway: Sending Email to {destination} (Background)...")
    if not SMTP_HOST: return
    try:
        msg = MIMEMultipart()
        msg['From'] = formataddr((sender_name, SMTP_FROM_EMAIL))
        msg['To'] = destination
        msg['Subject'] = subject 
        msg['Date'] = formatdate(localtime=True)
        msg['Message-ID'] = make_msgid(domain='syscall-sdk.com')
        msg.attach(MIMEText(content, 'plain'))

        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.ehlo()
            if server.has_extn("STARTTLS"):
                server.starttls(context=context)
                server.ehlo()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)
        logger.info(f"   >>> Gateway: Email Sent to {destination}")
    except Exception as e:
        logger.error(f"   !!! SMTP Error: {e}")

# ==========================================
#        BLOCKCHAIN LOGIC (VERIFIER)
# ==========================================

def verify_and_consume(tx_hash: str, secret: str):
    if not w3_global: return None
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

        if computed_hash != on_chain_commitment: return None
        if contract.functions.isConsumed(payment_id).call(): return None

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

    # [SECURITY] 1. Check Memory Cache
    if payload.tx_hash in PROCESSING_CACHE:
        logger.warning(f"⛔ REPLAY BLOCKED: TX {payload.tx_hash} is already processing.")
        raise HTTPException(status_code=409, detail="Transaction already processing")

    # [SECURITY] 2. Lock
    PROCESSING_CACHE.add(payload.tx_hash)

    try:
        # 3. Verify on Chain
        valid_payment = verify_and_consume(payload.tx_hash, payload.secret)
        
        if not valid_payment:
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
            if service_type == "email":
                # 4. Async Delivery
                background_tasks.add_task(
                    execute_email_delivery,
                    payload.destination, 
                    payload.subject, 
                    payload.sender_name, 
                    payload.content
                )
                provider_sid = "queued" 
            else:
                PROCESSING_CACHE.discard(payload.tx_hash)
                raise HTTPException(status_code=400, detail="Unknown Service (SMS Disabled)")
        except Exception as e:
             PROCESSING_CACHE.discard(payload.tx_hash)
             raise HTTPException(status_code=502, detail=str(e))

        # 5. Chain Update
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
    except Exception as e:
        PROCESSING_CACHE.discard(payload.tx_hash)
        raise e

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
