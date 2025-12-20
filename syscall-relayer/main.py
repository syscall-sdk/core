import logging
import sys
import os
from logging.handlers import RotatingFileHandler
from fastapi import FastAPI, Request, HTTPException
from pydantic import BaseModel
from web3 import Web3  # [NEW] Import Web3 for blockchain interaction
from web3.exceptions import TransactionNotFound

# --- Configuration ---

# MegaETH Testnet RPC (or any EVM RPC). 
# It is best practice to load this from an .env file.
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

class RelayPayload(BaseModel):
    target: str 
    message: str
    recipient: str

class VerificationPayload(BaseModel):
    tx_hash: str        # The mined transaction hash (Step 3)
    signature: str      # The user's cryptographic signature (Step 4)
    sender: str         # The wallet address

# --- Utility Functions ---

def verify_payment_on_chain(tx_hash: str) -> bool:
    """
    Step 5 Implementation:
    Connects to the RPC and verifies if the transaction is mined and successful.
    """
    try:
        # 1. Initialize Web3 connection
        w3 = Web3(Web3.HTTPProvider(RPC_URL))
        
        if not w3.is_connected():
            logger.critical(f"Failed to connect to RPC URL: {RPC_URL}")
            return False

        logger.debug(f"Querying RPC for TX: {tx_hash}")

        # 2. Get Transaction Receipt
        # This will raise TransactionNotFound if the TX is not on the chain yet
        try:
            tx_receipt = w3.eth.get_transaction_receipt(tx_hash)
        except TransactionNotFound:
            logger.warning(f"Transaction not found on chain: {tx_hash}")
            return False

        # 3. Verify Status (1 = Success, 0 = Fail)
        if tx_receipt['status'] == 1:
            logger.info(f"Chain Verification: TX {tx_hash} is SUCCESSFUL (Block: {tx_receipt['blockNumber']})")
            
            # (Optional) Advanced: Check if 'to' address matches your Syscall Contract
            # if tx_receipt['to'] != YOUR_CONTRACT_ADDRESS: return False
            
            return True
        else:
            logger.warning(f"Chain Verification: TX {tx_hash} FAILED (Status: 0)")
            return False

    except Exception as e:
        logger.error(f"Unexpected Web3 Error: {str(e)}")
        return False

# --- Endpoints ---

@app.on_event("startup")
async def startup_event():
    logger.info(">>> SERVICE SYSCALL-RELAYER STARTED <<<")
    logger.info(f"Connected to RPC: {RPC_URL}")

# [UPDATED] Step 4 Endpoint: Verify Transaction
@app.post("/verify")
async def verify_transaction(payload: VerificationPayload, request: Request):
    client_host = request.client.host
    logger.info(f"Verification request from {client_host} | TX: {payload.tx_hash}")
    
    # Step 5: Verify payment (Real Blockchain Check)
    payment_valid = verify_payment_on_chain(payload.tx_hash)

    if not payment_valid:
        logger.warning(f"Verification FAILED for TX: {payload.tx_hash}")
        raise HTTPException(status_code=400, detail="Transaction failed, not found, or RPC error")

    # Step 6: Return JWT (Mocked)
    logger.info(f"Payment verified for {payload.sender}. Issuing JWT.")
    return {
        "status": "success",
        "jwt": "eyJhGciOiJIUzI1Ni... (mock_token)",
        "message": "Payment verified, action authorized."
    }

# [EXISTING] Step 8 Endpoint: Execute Action
@app.post("/relay")
async def relay_message(payload: RelayPayload, request: Request):
    client_host = request.client.host
    logger.info(f"Relay request received from {client_host} | Target: {payload.target}")
    logger.debug(f"Full Payload: {payload.dict()}")

    if payload.target == "email":
        logger.info(f"DECISION: calling email-gateway for {payload.recipient}")
        # TODO: Implement HTTP call to email-gateway
    
    elif payload.target == "sms":
        logger.info(f"DECISION: calling sms-gateway for {payload.recipient}")
        # TODO: Implement HTTP call to sms-gateway
    
    else:
        logger.warning(f"Unknown target: {payload.target}")
        return {"status": "error", "message": "Unknown target"}

    return {"status": "success", "relayed_to": payload.target}
  
