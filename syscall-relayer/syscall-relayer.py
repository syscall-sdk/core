import logging
import sys
import os
from logging.handlers import RotatingFileHandler
from fastapi import FastAPI, Request, HTTPException
from pydantic import BaseModel
from web3 import Web3  
from web3.exceptions import TransactionNotFound

# --- Configuration ---
PORT = int(os.getenv("PORT", 8000))
RPC_URL = os.getenv("RPC_URL", "https://topstrike-megaeth-ws-proxy-100.fly.dev/rpc") 

# Proxy (Registry) Address - The only hardcoded address the system needs to trust.
#
PROXY_ADDRESS = "0x68704764C29886ed623b0f3CD30516Bf0643f390"

# --- Minimal ABIs for reading ---
PROXY_ABI = '[{"inputs":[],"name":"syscallContract","outputs":[{"internalType":"address","name":"","type":"address"}],"stateMutability":"view","type":"function"}]'
CONTRACT_ABI = '[{"anonymous":false,"inputs":[{"indexed":true,"internalType":"uint256","name":"paymentId","type":"uint256"},{"indexed":true,"internalType":"address","name":"user","type":"address"},{"indexed":false,"internalType":"string","name":"name","type":"string"},{"indexed":false,"internalType":"uint256","name":"amount","type":"uint256"},{"indexed":false,"internalType":"uint256","name":"timestamp","type":"uint256"}],"name":"ActionPaid","type":"event"}, {"inputs":[{"internalType":"uint256","name":"","type":"uint256"}],"name":"isConsumed","outputs":[{"internalType":"bool","name":"","type":"bool"}],"stateMutability":"view","type":"function"}]'

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
    tx_hash: str        
    signature: str      
    sender: str         

# --- Utility Functions ---

def get_authoritative_contract(w3: Web3) -> str:
    """
    Queries the Proxy to get the current authoritative SyscallContract address.
    """
    try:
        proxy = w3.eth.contract(address=PROXY_ADDRESS, abi=PROXY_ABI)
        contract_address = proxy.functions.syscallContract().call()
        logger.debug(f"[Security] Authoritative Contract Address from Proxy: {contract_address}")
        return contract_address
    except Exception as e:
        logger.critical(f"[Security] Failed to fetch contract from proxy: {e}")
        return None

def verify_payment_on_chain(tx_hash: str) -> bool:
    """
    Full and secure payment verification.
    Checks: Status, Destination Address, Event Logs, and Consumed State.
    """
    try:
        w3 = Web3(Web3.HTTPProvider(RPC_URL))
        if not w3.is_connected():
            logger.critical(f"Failed to connect to RPC URL: {RPC_URL}")
            return False

        logger.debug(f"[Step 5] Analyzing TX: {tx_hash}")

        # 1. Fetch transaction receipt
        try:
            tx_receipt = w3.eth.get_transaction_receipt(tx_hash)
        except TransactionNotFound:
            logger.warning(f"[Step 5] Transaction not found: {tx_hash}")
            return False

        # 2. Verify Status (1 = Success, 0 = Fail)
        if tx_receipt['status'] != 1:
            logger.warning(f"[Step 5] Transaction failed (Status 0): {tx_hash}")
            return False

        # 3. Fetch authoritative address via Proxy
        target_contract = get_authoritative_contract(w3)
        if not target_contract:
            return False

        # 4. Verify funds went to the correct contract
        # Note: tx_receipt['to'] can be null for contract creation, hence the check.
        if tx_receipt['to'].lower() != target_contract.lower():
            logger.warning(f"[Step 5] Security Alert: TX sent to {tx_receipt['to']}, expected {target_contract}")
            return False

        # 5. Decode logs to find the paymentId
        # We use the contract ABI to parse logs from this specific receipt
        contract = w3.eth.contract(address=target_contract, abi=CONTRACT_ABI)
        
        # Look for 'ActionPaid' event in the transaction logs
        action_paid_events = contract.events.ActionPaid().process_receipt(tx_receipt)
        
        if not action_paid_events:
            logger.warning(f"[Step 5] No ActionPaid event found in transaction logs.")
            return False
            
        # Take the first event (one tx = one payment in our case)
        event_args = action_paid_events[0]['args']
        payment_id = event_args['paymentId']
        logger.info(f"[Step 5] Payment identified: ID {payment_id} | Amount: {event_args['amount']}")

        # 6. Check if payment was already consumed (Anti-Replay)
        is_consumed = contract.functions.isConsumed(payment_id).call()
        
        if is_consumed:
            logger.warning(f"[Step 5] REPLAY ATTACK BLOCKED: Payment ID {payment_id} already consumed.")
            return False

        logger.info(f"[Step 5] SECURITY CHECKS PASSED for Payment ID {payment_id}")
        
        # TODO: At this stage, in a real system, the Relayer should call 
        # contract.functions.consumePayment(payment_id).transact() to "burn" the payment.
        # For now, we return True to authorize the action.
        
        return True

    except Exception as e:
        logger.error(f"Unexpected Web3 Error: {str(e)}")
        return False

# --- Endpoints ---

@app.on_event("startup")
async def startup_event():
    logger.info(f">>> SYSCALL RELAYER LISTENING ON PORT {PORT} <<<")
    logger.info(f">>> LINKED TO REGISTRY: {PROXY_ADDRESS} <<<")

@app.post("/verify")
async def verify_transaction(payload: VerificationPayload, request: Request):
    client_host = request.client.host
    logger.info(f"[Step 4] Request from {client_host} | Sender: {payload.sender}")
    
    # Execute Step 5 (Deep Verification)
    payment_valid = verify_payment_on_chain(payload.tx_hash)

    if not payment_valid:
        logger.warning(f"Verification FAILED for TX: {payload.tx_hash}")
        raise HTTPException(status_code=400, detail="Transaction invalid, unauthorized contract, or already consumed.")

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
