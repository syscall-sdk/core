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

# --- Configuration ---
PORT = int(os.getenv("PORT", 8080))
RPC_URL = os.getenv("RPC_URL", "https://topstrike-megaeth-ws-proxy-100.fly.dev/rpc")
OWNER_PRIVATE_KEY = os.getenv("OWNER_PRIVATE_KEY")
PROXY_ADDRESS = os.getenv("PROXY_ADDRESS", "0x68704764C29886ed623b0f3CD30516Bf0643f390")
JWT_SECRET = os.getenv("JWT_SECRET", "super-secret-syscall-key-2026")

# --- ABIs ---
PROXY_ABI = '[{"inputs":[],"name":"syscallContract","outputs":[{"internalType":"address","name":"","type":"address"}],"stateMutability":"view","type":"function"}]'

# UPDATED ABI: ActionPaid now includes 'quantity' (uint256)
CONTRACT_ABI = '[{"anonymous":false,"inputs":[{"indexed":true,"internalType":"uint256","name":"paymentId","type":"uint256"},{"indexed":true,"internalType":"address","name":"user","type":"address"},{"indexed":false,"internalType":"string","name":"name","type":"string"},{"indexed":false,"internalType":"uint256","name":"amount","type":"uint256"},{"indexed":false,"internalType":"uint256","name":"quantity","type":"uint256"},{"indexed":false,"internalType":"uint256","name":"timestamp","type":"uint256"}],"name":"ActionPaid","type":"event"}, {"inputs":[{"internalType":"uint256","name":"","type":"uint256"}],"name":"isConsumed","outputs":[{"internalType":"bool","name":"","type":"bool"}],"stateMutability":"view","type":"function"}, {"inputs":[{"internalType":"uint256","name":"paymentId","type":"uint256"}],"name":"consumePayment","outputs":[],"stateMutability":"nonpayable","type":"function"}]'

# --- Logger ---
if not os.path.exists("logs"): os.makedirs("logs")
logger = logging.getLogger("syscall-relayer")
logger.setLevel(logging.DEBUG) 
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setFormatter(formatter)
logger.addHandler(stream_handler)

app = FastAPI(title="Syscall Relayer", version="0.3.0-beta")

# --- Models ---
class VerificationPayload(BaseModel):
    tx_hash: str        
    signature: str      
    sender: str         

class DispatchPayload(BaseModel):
    destination: str 
    content: str      

# --- Blockchain Logic ---

def get_authoritative_contract(w3: Web3) -> str:
    try:
        proxy = w3.eth.contract(address=PROXY_ADDRESS, abi=PROXY_ABI)
        return proxy.functions.syscallContract().call()
    except Exception as e:
        logger.critical(f"Proxy Error: {e}")
        return None

def verify_payment_on_chain(tx_hash: str):
    """ Read-Only: Checks if payment exists and returns the purchased capacity (quantity). """
    try:
        w3 = Web3(Web3.HTTPProvider(RPC_URL))
        if not w3.is_connected(): return None

        try:
            tx_receipt = w3.eth.get_transaction_receipt(tx_hash)
        except TransactionNotFound: return None

        if tx_receipt['status'] != 1: return None

        target_contract = get_authoritative_contract(w3)
        contract = w3.eth.contract(address=target_contract, abi=CONTRACT_ABI)
        
        # Parse logs to find ActionPaid
        action_paid_events = contract.events.ActionPaid().process_receipt(tx_receipt)
        if not action_paid_events: return None
            
        event_args = action_paid_events[0]['args']
        payment_id = event_args['paymentId']
        quantity = event_args.get('quantity', 0) # The capacity purchased

        # Check consumption status 
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
    """ 
    Write Operation: Calls consumePayment(paymentId).
    AUTO-GAS: Calculates gas limit and price dynamically for any EVM chain.
    """
    if not OWNER_PRIVATE_KEY:
        logger.error("Owner Private Key not found. Cannot mark consumed.")
        return None

    try:
        w3 = Web3(Web3.HTTPProvider(RPC_URL))
        account = Account.from_key(OWNER_PRIVATE_KEY)
        target_contract = get_authoritative_contract(w3)
        contract = w3.eth.contract(address=target_contract, abi=CONTRACT_ABI)

        # 1. Prepare the function call
        contract_function = contract.functions.consumePayment(payment_id)
        
        # 2. Get current Nonce
        nonce = w3.eth.get_transaction_count(account.address, 'pending')

        # 3. Dynamic Gas Price (Universal Strategy)
        # We fetch the current gas price from the network. 
        # This works for both Legacy chains and EIP-1559 chains (as a fallback).
        current_gas_price = w3.eth.gas_price

        # 4. Dynamic Gas Limit (Estimation + Safety Buffer)
        # We simulate the transaction to see how much gas it actually needs.
        try:
            estimated_gas = contract_function.estimate_gas({
                'from': account.address, 
                'nonce': nonce,
                'value': 0
            })
            # Add a 20% buffer for safety (x1.2)
            gas_limit = int(estimated_gas * 1.2)
        except Exception as e:
            # Fallback if estimation fails (e.g. rarely on some L2s)
            logger.warning(f"Gas estimation failed, using fallback: {e}")
            gas_limit = 300000 

        # 5. Build the final transaction
        tx_params = {
            'from': account.address,
            'nonce': nonce,
            'gas': gas_limit,
            'gasPrice': current_gas_price,
            'chainId': w3.eth.chain_id
        }
        
        # Build
        tx = contract_function.build_transaction(tx_params)

        # 6. Sign & Send
        signed_tx = w3.eth.account.sign_transaction(tx, OWNER_PRIVATE_KEY)
        tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)
        
        # Wait for receipt
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
        
        if receipt.status == 1:
            # Calculate actual cost for logging (Optional but useful)
            cost_eth = w3.from_wei(receipt.gasUsed * current_gas_price, 'ether')
            logger.info(f"On-Chain Consumption Success: TX {tx_hash.hex()} | Cost: {cost_eth:.6f} ETH")
            return tx_hash.hex()
        else:
            logger.error("On-Chain Consumption Failed (Reverted)")
            return None

    except Exception as e:
        logger.error(f"Blockchain Write Error: {e}")
        return None

# --- Endpoints ---

@app.post("/verify")
async def verify_transaction(payload: VerificationPayload, request: Request):
    """ [Step 4 -> 6] Verify Payment & Issue JWT """
    logger.info(f"[Step 4] Verification Request: {payload.tx_hash}")
    
    payment_data = verify_payment_on_chain(payload.tx_hash)
    if not payment_data:
        raise HTTPException(status_code=400, detail="Invalid Payment or Already Consumed")

    # Generate JWT with purchased quantity
    token_payload = {
        "iss": "syscall-relayer",
        "sub": payment_data["user"],
        "pid": payment_data["paymentId"],
        "svc": payment_data["service"],
        "qty": payment_data["quantity"], # Embed quantity in token
        "iat": int(time.time()),
        "exp": int(time.time()) + 300
    }
    
    token = jwt.encode(token_payload, JWT_SECRET, algorithm="HS256")
    logger.info(f"[Step 6] JWT Issued for Payment {payment_data['paymentId']}")

    return {"status": "authorized", "jwt": token}

@app.post("/dispatch")
async def dispatch_action(payload: DispatchPayload, authorization: str = Header(None)):
    """ 
    [Step 7] Gateway Logic: Check JWT, Check Length & Execute 
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer Token")

    token = authorization.split(" ")[1]

    try:
        decoded = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        payment_id = decoded.get("pid")
        service_type = decoded.get("svc")
        allowed_quantity = decoded.get("qty", 0) # Retrieve purchased limit
        
        # --- NEW SECURITY CHECK: CONTENT LENGTH ---
        content_length = len(payload.content.encode('utf-8'))
        if content_length > allowed_quantity:
            logger.warning(f"Fraud Attempt: Paid for {allowed_quantity}, sent {content_length}")
            raise HTTPException(status_code=402, detail=f"Content too long. Paid for {allowed_quantity} bytes.")

        logger.info(f"[Step 7] Dispatching {service_type.upper()} for Payment ID {payment_id}")

        # --- A. GATEWAY SIMULATION ---
        logger.info(f"   >>> Sending '{payload.content}' to {payload.destination}")
        time.sleep(1) 

        # --- B. BLOCKCHAIN CONSUMPTION ---
        logger.info(f"   >>> Marking Payment {payment_id} as consumed on-chain...")
        consume_tx = mark_consumed_on_chain(payment_id)
        
        if not consume_tx:
            logger.warning("   !!! Failed to mark consumed on-chain")

        # --- C. [Step 9] ACKNOWLEDGMENT ---
        logger.info(f"[Step 9] Returning ACK to SDK")
        
        return {
            "status": "success",
            "service": service_type,
            "destination": payload.destination,
            "meta": {
                "paymentId": payment_id,
                "consumptionTx": consume_tx, 
                "timestamp": int(time.time())
            }
        }

    except jwt.ExpiredSignatureError: raise HTTPException(status_code=401, detail="Token Expired")
    except jwt.InvalidTokenError: raise HTTPException(status_code=401, detail="Invalid Token")

if __name__ == "__main__":
    import uvicorn
    # Make sure to install dependencies: pip install uvicorn fastapi web3 pyjwt eth-account
    uvicorn.run(app, host="0.0.0.0", port=PORT)
