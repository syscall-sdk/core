import logging
import sys
import os
import smtplib
import ssl
from contextlib import asynccontextmanager
from email.utils import make_msgid, formatdate, formataddr
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from fastapi import FastAPI, HTTPException, BackgroundTasks
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

PORT = int(os.getenv("SYSCALL-EMAIL-RELAYER-PORT", 8080))
RPC_URL = os.getenv("SYSCALL-EMAIL-RELAYER-RPC_URL")
OWNER_PRIVATE_KEY = os.getenv("SYSCALL-EMAIL-RELAYER-OWNER_PRIVATE_KEY")
SYSCALL_CONTRACT_ADDRESS = os.getenv("SYSCALL-EMAIL-RELAYER-SYSCALL_CONTRACT_ADDRESS")

# NOTE: CHAIN_ID supprimé du .env. On le récupère dynamiquement du RPC.

# EMAIL Config
SMTP_HOST = os.getenv("SYSCALL-EMAIL-RELAYER-SMTP_HOST") 
SMTP_PORT = int(os.getenv("SYSCALL-EMAIL-RELAYER-SMTP_PORT", 587))
SMTP_USER = os.getenv("SYSCALL-EMAIL-RELAYER-SMTP_USER")                 
SMTP_PASSWORD = os.getenv("SYSCALL-EMAIL-RELAYER-SMTP_PASSWORD")
SMTP_FROM_EMAIL = os.getenv("SYSCALL-EMAIL-RELAYER-SMTP_FROM_EMAIL")

# [SECURITY] Hard limit for Email payload to prevent OOM (1MB)
MAX_PAYLOAD_SIZE_BYTES = 1024 * 1024 

CONTRACT_ABI = '[{"anonymous":false,"inputs":[{"indexed":true,"internalType":"uint256","name":"paymentId","type":"uint256"},{"indexed":true,"internalType":"address","name":"user","type":"address"},{"indexed":false,"internalType":"string","name":"name","type":"string"},{"indexed":false,"internalType":"uint256","name":"amount","type":"uint256"},{"indexed":false,"internalType":"uint256","name":"quantity","type":"uint256"},{"indexed":false,"internalType":"bytes32","name":"commitment","type":"bytes32"},{"indexed":false,"internalType":"uint256","name":"timestamp","type":"uint256"}],"name":"ActionPaid","type":"event"}, {"inputs":[{"internalType":"uint256","name":"","type":"uint256"}],"name":"isConsumed","outputs":[{"internalType":"bool","name":"","type":"bool"}],"stateMutability":"view","type":"function"}, {"inputs":[{"internalType":"uint256","name":"paymentId","type":"uint256"}],"name":"consumePayment","outputs":[],"stateMutability":"nonpayable","type":"function"}]'

# --- Logger ---
if not os.path.exists("logs"): os.makedirs("logs")
logger = logging.getLogger("syscall-relayer")
logger.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setFormatter(formatter)
logger.addHandler(stream_handler)

# Global State
w3_global = None
REAL_CHAIN_ID = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- STARTUP ---
    global w3_global, REAL_CHAIN_ID
    try:
        w3_global = Web3(Web3.HTTPProvider(RPC_URL))
        if w3_global.is_connected():
            REAL_CHAIN_ID = w3_global.eth.chain_id
            logger.info(f"✅ Connected to RPC: {RPC_URL}")
            logger.info(f"🔗 Detected Chain ID: {REAL_CHAIN_ID}")
        else:
            logger.warning(f"⚠️ Failed to connect to RPC")
    except Exception as e:
        logger.error(f"❌ RPC Connection Error: {e}")
    
    yield # App running
    
    # --- SHUTDOWN ---
    logger.info("🔌 System Shutdown.")

app = FastAPI(title="Syscall Relayer (Email Secure)", version="3.2.0", lifespan=lifespan)

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

PROCESSING_CACHE = set()

# ==========================================
#           CORE LOGIC (GATEWAY)
# ==========================================

def execute_email_delivery(destination: str, subject: str, sender_name: str, content: str):
    logger.info(f"   >>> Gateway: Sending Email to {destination} (Background)...")
    if not SMTP_HOST: 
        logger.error("❌ SMTP Config missing.")
        return

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

        return {"paymentId": payment_id, "service": service, "quantity": quantity}

    except Exception as e:
        logger.error(f"Verification Error: {str(e)}")
        return None

def mark_consumed_on_chain(payment_id: int):
    if not OWNER_PRIVATE_KEY or not w3_global: return None
    try:
        account = Account.from_key(OWNER_PRIVATE_KEY)
        contract = w3_global.eth.contract(address=Web3.to_checksum_address(SYSCALL_CONTRACT_ADDRESS), abi=CONTRACT_ABI)
        func = contract.functions.consumePayment(payment_id)
        
        tx_params = {
            'from': account.address,
            'nonce': w3_global.eth.get_transaction_count(account.address, 'pending'),
            'gas': 300000,
            'gasPrice': w3_global.eth.gas_price,
            'chainId': w3_global.eth.chain_id # Déjà dynamique ici, correct.
        }
        
        signed = w3_global.eth.account.sign_transaction(func.build_transaction(tx_params), OWNER_PRIVATE_KEY)
        tx_hash = w3_global.eth.send_raw_transaction(signed.rawTransaction) # Correction camelCase préventive si web3 > v6
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
    # Renvoie l'ID réel détecté
    return { "rpc_url": RPC_URL, "contract_address": safe_addr, "chain_id": REAL_CHAIN_ID }

@app.post("/dispatch")
async def dispatch_action(payload: DispatchPayload, background_tasks: BackgroundTasks):
    logger.info(f"Received Dispatch Request for TX: {payload.tx_hash}")

    if payload.tx_hash in PROCESSING_CACHE:
        raise HTTPException(status_code=409, detail="Transaction already processing")

    if len(payload.content) > MAX_PAYLOAD_SIZE_BYTES:
        logger.warning(f"DoS Blocked: Payload size {len(payload.content)} exceeds 1MB limit.")
        raise HTTPException(status_code=413, detail="Payload content too large for Email Relay.")

    PROCESSING_CACHE.add(payload.tx_hash)

    try:
        valid_payment = verify_and_consume(payload.tx_hash, payload.secret)
        if not valid_payment:
            raise HTTPException(status_code=400, detail="Invalid Payment, Bad Secret, or Replay")

        payload_size = len(payload.content.encode('utf-8'))
        paid_quantity = valid_payment['quantity']

        if payload_size > paid_quantity:
            logger.warning(f"Validation Failed: Paid {paid_quantity}, sent {payload_size}.")
            raise HTTPException(status_code=402, detail=f"Content size ({payload_size}) exceeds paid quantity ({paid_quantity})")

        if valid_payment['service'] == "email":
            background_tasks.add_task(
                execute_email_delivery,
                payload.destination, 
                payload.subject, 
                payload.sender_name, 
                payload.content
            )
        else:
            raise HTTPException(status_code=400, detail="Unknown Service")

        tx = mark_consumed_on_chain(valid_payment['paymentId'])
        
        return {
            "status": "success",
            "meta": {
                "paymentId": valid_payment['paymentId'],
                "consumptionTx": tx
            }
        }

    except Exception as e:
        raise e
        
    finally:
        PROCESSING_CACHE.discard(payload.tx_hash)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
