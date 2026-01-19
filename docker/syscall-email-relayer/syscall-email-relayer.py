import logging
import sys
import os
import asyncio
import re
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from web3 import Web3
from web3.exceptions import TransactionNotFound
from eth_account import Account
from eth_utils import keccak
import slixmpp

# ==========================================
#              CONFIGURATION
# ==========================================

PORT = int(os.getenv("SYSCALL-SMS-RELAYER-PORT", 8080))
RPC_URL = os.getenv("SYSCALL-SMS-RELAYER-RPC_URL")
OWNER_PRIVATE_KEY = os.getenv("SYSCALL-SMS-RELAYER-OWNER_PRIVATE_KEY")
SYSCALL_CONTRACT_ADDRESS = os.getenv("SYSCALL-SMS-RELAYER-SYSCALL_CONTRACT_ADDRESS")

CHAIN_ID_ENV = os.getenv("SYSCALL-SMS-RELAYER-CHAIN_ID")
if not CHAIN_ID_ENV:
    raise ValueError("CRITICAL ERROR: 'SYSCALL-SMS-RELAYER-CHAIN_ID' is missing.")
CHAIN_ID = int(CHAIN_ID_ENV)

# [JMP.CHAT / XMPP CONFIG]
JMP_JID = os.getenv("SYSCALL-SMS-RELAYER-JMP_JID")       
JMP_PASSWORD = os.getenv("SYSCALL-SMS-RELAYER-JMP_PASSWORD") 
JMP_GATEWAY_SUFFIX = os.getenv("SYSCALL-SMS-RELAYER-JMP_GATEWAY_SUFFIX", "cheogram.com")

# [SECURITY] Hard limit for SMS payload (approx 10 segments)
MAX_PAYLOAD_SIZE_BYTES = 2048 

CONTRACT_ABI = '[{"anonymous":false,"inputs":[{"indexed":true,"internalType":"uint256","name":"paymentId","type":"uint256"},{"indexed":true,"internalType":"address","name":"user","type":"address"},{"indexed":false,"internalType":"string","name":"name","type":"string"},{"indexed":false,"internalType":"uint256","name":"amount","type":"uint256"},{"indexed":false,"internalType":"uint256","name":"quantity","type":"uint256"},{"indexed":false,"internalType":"bytes32","name":"commitment","type":"bytes32"},{"indexed":false,"internalType":"uint256","name":"timestamp","type":"uint256"}],"name":"ActionPaid","type":"event"}, {"inputs":[{"internalType":"uint256","name":"","type":"uint256"}],"name":"isConsumed","outputs":[{"internalType":"bool","name":"","type":"bool"}],"stateMutability":"view","type":"function"}, {"inputs":[{"internalType":"uint256","name":"paymentId","type":"uint256"}],"name":"consumePayment","outputs":[],"stateMutability":"nonpayable","type":"function"}]'

# --- Logger ---
if not os.path.exists("logs"): os.makedirs("logs")
logger = logging.getLogger("syscall-relayer")
logger.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setFormatter(formatter)
logger.addHandler(stream_handler)

# ==========================================
#        JMP/XMPP CLIENT (LIFESPAN)
# ==========================================

class SyscallXMPP(slixmpp.ClientXMPP):
    def __init__(self, jid, password):
        super().__init__(jid, password)
        self.auth_event = asyncio.Event() 
        self.add_event_handler("session_start", self.start)
        self.add_event_handler("disconnected", self.on_disconnect)
        self.register_plugin('xep_0199') # Ping

    async def start(self, event):
        self.send_presence()
        await self.get_roster()
        self.auth_event.set() 
        logger.info("✅ XMPP Connected & Authenticated (Ready to Send)")

    def on_disconnect(self, event):
        self.auth_event.clear()
        logger.warning("⚠️ XMPP Disconnected.")

# Global Client Placeholder
xmpp_client = None
w3_global = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- STARTUP ---
    global xmpp_client, w3_global
    
    # 1. Init Web3
    try:
        w3_global = Web3(Web3.HTTPProvider(RPC_URL))
        if w3_global.is_connected():
            logger.info(f"✅ Connected to RPC: {RPC_URL}")
        else:
            logger.warning(f"⚠️ Failed to connect to RPC")
    except Exception as e:
        logger.error(f"❌ RPC Connection Error: {e}")

    # 2. Init XMPP
    if JMP_JID and JMP_PASSWORD:
        logger.info(f"🔌 Connecting to XMPP ({JMP_JID})...")
        xmpp_client = SyscallXMPP(JMP_JID, JMP_PASSWORD)
        xmpp_client.connect() # Background connection
        
        # Wait for auth with timeout
        try:
            await asyncio.wait_for(xmpp_client.auth_event.wait(), timeout=10.0)
        except asyncio.TimeoutError:
            logger.error("❌ XMPP Timeout: Could not authenticate in time.")
    
    yield # App running
    
    # --- SHUTDOWN ---
    if xmpp_client:
        logger.info("🔌 Disconnecting XMPP...")
        xmpp_client.disconnect()

app = FastAPI(title="Syscall Relayer (JMP XMPP Elite)", version="3.3.3", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex="https?://.*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")

class DispatchPayload(BaseModel):
    tx_hash: str
    secret: str         
    destination: str
    content: str
    subject: str = "SMS"     
    sender_name: str = "SDK" 

PROCESSING_CACHE = set()

# ==========================================
#           CORE LOGIC (GATEWAY)
# ==========================================

async def execute_sms_delivery_xmpp(destination: str, content: str):
    logger.info(f"   >>> Gateway: Routing SMS to {destination} via XMPP...")
    
    if not xmpp_client:
        logger.error("❌ XMPP Client not initialized.")
        return

    # Active wait for reconnection
    if not xmpp_client.auth_event.is_set():
        logger.warning("   ... Waiting for XMPP Reconnection ...")
        try:
            await asyncio.wait_for(xmpp_client.auth_event.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            logger.error("❌ Failed to send: XMPP Disconnected")
            return

    # [SECURITY CRITICAL] Input Sanitization & Access Control
    # 1. Strip whitespace
    clean_dest = destination.strip()
    
    # 2. Strict Phone Number Validation (E.164-like)
    # Prevents injection of JIDs, emails, or malicious characters.
    # Allows only +, digits. Min length 7, max 15.
    if not re.match(r"^\+?[1-9]\d{6,14}$", clean_dest):
        logger.warning(f"⛔ Security Block: Invalid Phone Number format '{clean_dest}'. SMS Rejected.")
        return

    # 3. Force Gateway Suffix (Prevent Open Relay)
    # This prevents users from routing messages to arbitrary XMPP/Jabber addresses.
    # We ignore any existing '@' and strictly append the gateway suffix.
    target_jid = f"{clean_dest}@{JMP_GATEWAY_SUFFIX}"

    try:
        xmpp_client.send_message(mto=target_jid, mbody=content, mtype='chat')
        logger.info(f"   >>> Gateway: Message dispatched to {target_jid}")
    except Exception as e:
        logger.error(f"   !!! XMPP Send Error: {e}")

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
    except Exception: return None

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
    return { "rpc_url": RPC_URL, "contract_address": safe_addr, "chain_id": CHAIN_ID }

@app.post("/dispatch")
async def dispatch_action(payload: DispatchPayload, background_tasks: BackgroundTasks):
    logger.info(f"Received Dispatch Request for TX: {payload.tx_hash}")

    if payload.tx_hash in PROCESSING_CACHE:
        raise HTTPException(status_code=409, detail="Transaction already processing")
    
    # [SECURITY] 1. Pre-computation sanity check (DoS protection)
    if len(payload.content) > MAX_PAYLOAD_SIZE_BYTES:
        logger.warning(f"DoS Blocked: Payload size {len(payload.content)} exceeds limit.")
        raise HTTPException(status_code=413, detail="Payload content too large for SMS.")

    PROCESSING_CACHE.add(payload.tx_hash)

    try:
        valid_payment = verify_and_consume(payload.tx_hash, payload.secret)
        if not valid_payment:
            raise HTTPException(status_code=400, detail="Invalid Payment")

        # [SECURITY] 2. Logic Validation (Pay-for-what-you-use)
        payload_size = len(payload.content.encode('utf-8'))
        paid_quantity = valid_payment['quantity']

        if payload_size > paid_quantity:
            logger.warning(f"Validation Failed: Paid {paid_quantity}, sent {payload_size}.")
            raise HTTPException(status_code=402, detail="Content size exceeds paid quantity.")

        # SMS Logic
        if valid_payment['service'] == "sms":
            background_tasks.add_task(execute_sms_delivery_xmpp, payload.destination, payload.content)
        else:
            raise HTTPException(status_code=400, detail="Unknown Service")

        tx = mark_consumed_on_chain(valid_payment['paymentId'])
        return {"status": "success", "meta": {"paymentId": valid_payment['paymentId'], "consumptionTx": tx}}
        
    except Exception as e:
        raise e
        
    finally:
        # [CRITICAL FIX] Memory Leak Prevention
        PROCESSING_CACHE.discard(payload.tx_hash)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
