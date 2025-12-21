import logging
import sys
import os
from logging.handlers import RotatingFileHandler
from fastapi import FastAPI, Request, HTTPException
from pydantic import BaseModel
from web3 import Web3  
from web3.exceptions import TransactionNotFound

# --- Configuration ---
# Ensure this matches your Docker setup (usually port 8000 or 8080)
PORT = int(os.getenv("PORT", 8000))
RPC_URL = os.getenv("RPC_URL", "https://topstrike-megaeth-ws-proxy-100.fly.dev/rpc") 

# --- Logger Configuration ---
if not os.path.exists("logs"):
    os.makedirs("logs")

logger = logging.getLogger("syscall-relayer")
logger.setLevel(logging.DEBUG) 

formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setFormatter(formatter)
logger.addHandler(stream_handler)

file_handler = RotatingFileHandler('logs/activity.log', maxBytes=5*1024*1024, backupCount=5)
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

# --- API Application ---
app = FastAPI(title="Syscall Relayer", version="0.1.0-alpha")

# --- Data Models ---
class VerificationPayload(BaseModel):
    tx_hash: str        # Step 4: The mined transaction hash
    signature: str      # Step 4: The user's signature
    sender: str         # Step 4: The user's wallet address

# --- Utility Functions ---

def verify_payment_on_chain(tx_hash: str) -> bool:
    """
    [Step 5] Verify Payment
    Connects to the RPC and confirms the transaction was mined successfully.
    """
    try:
        w3 = Web3(Web3.HTTPProvider(RPC_URL))
        
        if not w3.is_connected():
            logger.critical(f"Failed to connect to RPC URL: {RPC_URL}")
            return False

        logger.debug(f"[Step 5] Querying RPC for TX: {tx_hash}")

        try:
            tx_receipt = w3.eth.get_transaction_receipt(tx_hash)
        except TransactionNotFound:
            logger.warning(f"[Step 5] Transaction not found on chain: {tx_hash}")
            return False

        # Status 1 means success, 0 means revert
        if tx_receipt['status'] == 1:
            logger.info(f"[Step 5] SUCCESS: TX {tx_hash} is valid (Block: {tx_receipt['blockNumber']})")
            return True
        else:
            logger.warning(f"[Step 5] FAILED: TX {tx_hash} status is 0 (Reverted)")
            return False

    except Exception as e:
        logger.error(f"Unexpected Web3 Error: {str(e)}")
        return False

# --- Endpoints ---

@app.on_event("startup")
async def startup_event():
    logger.info(f">>> SYSCALL RELAYER LISTENING ON PORT {PORT} <<<")

@app.post("/verify")
async def verify_transaction(payload: VerificationPayload, request: Request):
    """
    [Step 4] Receive Sig + TxHash
    [Step 5] Verify Payment
    [Step 6] Return JWT (Mocked)
    """
    client_host = request.client.host
    logger.info(f"[Step 4] Received verification request from {client_host} | Sender: {payload.sender}")
    logger.debug(f"[Step 4] Payload: {payload.dict()}")
    
    # Execute Step 5
    payment_valid = verify_payment_on_chain(payload.tx_hash)

    if not payment_valid:
        logger.warning(f"Verification FAILED for TX: {payload.tx_hash}")
        raise HTTPException(status_code=400, detail="Transaction failed or not found on-chain")

    # Step 6: Return JWT (Simulated)
    logger.info(f"[Step 6] Issuing JWT for {payload.sender}")
    return {
        "status": "success",
        "jwt": "eyJhGciOiJIUzI1Ni... (mock_token)",
        "message": "Payment verified, relay authorized."
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
