import logging
import sys
import os
import time
import jwt  # [IMPORTANT] Requires: pip install pyjwt
from logging.handlers import RotatingFileHandler
from fastapi import FastAPI, Request, HTTPException, Header
from pydantic import BaseModel
from web3 import Web3  
from web3.exceptions import TransactionNotFound

# --- Configuration ---
PORT = int(os.getenv("PORT", 8000))
RPC_URL = os.getenv("RPC_URL", "https://topstrike-megaeth-ws-proxy-100.fly.dev/rpc") 
PROXY_ADDRESS = "0x68704764C29886ed623b0f3CD30516Bf0643f390"
JWT_SECRET = os.getenv("JWT_SECRET", "super-secret-syscall-key-2026") # Secret key for signing

# --- ABIs ---
PROXY_ABI = '[{"inputs":[],"name":"syscallContract","outputs":[{"internalType":"address","name":"","type":"address"}],"stateMutability":"view","type":"function"}]'
CONTRACT_ABI = '[{"anonymous":false,"inputs":[{"indexed":true,"internalType":"uint256","name":"paymentId","type":"uint256"},{"indexed":true,"internalType":"address","name":"user","type":"address"},{"indexed":false,"internalType":"string","name":"name","type":"string"},{"indexed":false,"internalType":"uint256","name":"amount","type":"uint256"},{"indexed":false,"internalType":"uint256","name":"timestamp","type":"uint256"}],"name":"ActionPaid","type":"event"}, {"inputs":[{"internalType":"uint256","name":"","type":"uint256"}],"name":"isConsumed","outputs":[{"internalType":"bool","name":"","type":"bool"}],"stateMutability":"view","type":"function"}]'

# --- Logger ---
if not os.path.exists("logs"): os.makedirs("logs")
logger = logging.getLogger("syscall-relayer")
logger.setLevel(logging.DEBUG) 
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setFormatter(formatter)
logger.addHandler(stream_handler)

app = FastAPI(title="Syscall Relayer", version="0.1.0-alpha")

# --- Models ---
class VerificationPayload(BaseModel):
    tx_hash: str        
    signature: str      
    sender: str         

class DispatchPayload(BaseModel):
    destination: str 
    content: str      

# --- Logic ---
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
        if not target_contract or tx_receipt['to'].lower() != target_contract.lower():
            logger.warning(f"Security Alert: Invalid contract destination.")
            return None

        contract = w3.eth.contract(address=target_contract, abi=CONTRACT_ABI)
        action_paid_events = contract.events.ActionPaid().process_receipt(tx_receipt)
        
        if not action_paid_events: return None
            
        event_args = action_paid_events[0]['args']
        
        if contract.functions.isConsumed(event_args['paymentId']).call():
            logger.warning(f"Replay Attempt: Payment {event_args['paymentId']} already consumed.")
            return None

        logger.info(f"Payment Validated: ID {event_args['paymentId']} | Service: {event_args['name']}")
        
        return {
            "paymentId": event_args['paymentId'],
            "service": event_args['name'],
            "user": event_args['user']
        }
    except Exception as e:
        logger.error(f"Web3 Error: {str(e)}")
        return None

# --- Endpoints ---

@app.post("/verify")
async def verify_transaction(payload: VerificationPayload, request: Request):
    """ [Step 6] Generate JWT """
    logger.info(f"[Step 4] Verification Request: {payload.tx_hash}")
    
    payment_data = verify_payment_on_chain(payload.tx_hash)
    if not payment_data:
        raise HTTPException(status_code=400, detail="Invalid Payment")

    # Generate JWT
    token_payload = {
        "iss": "syscall-relayer",
        "sub": payment_data["user"],
        "pid": payment_data["paymentId"],
        "svc": payment_data["service"],
        "iat": int(time.time()),
        "exp": int(time.time()) + 300
    }
    
    token = jwt.encode(token_payload, JWT_SECRET, algorithm="HS256")
    logger.info(f"[Step 6] JWT Issued for Payment {payment_data['paymentId']}")

    return {"status": "authorized", "jwt": token}

@app.post("/dispatch")
async def dispatch_action(payload: DispatchPayload, authorization: str = Header(None)):
    """ [Step 7] Gateway Logic: Check JWT & Execute """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer Token")

    token = authorization.split(" ")[1]

    try:
        decoded = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        logger.info(f"[Step 7] Gateway received valid JWT. Intent: Send {decoded.get('svc')} to {payload.destination}")

        # [Step 8] Simulation of sending
        return {
            "status": "delivered",
            "service": decoded.get("svc"),
            "timestamp": int(time.time())
        }

    except jwt.ExpiredSignatureError: raise HTTPException(status_code=401, detail="Token Expired")
    except jwt.InvalidTokenError: raise HTTPException(status_code=401, detail="Invalid Token")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
    
