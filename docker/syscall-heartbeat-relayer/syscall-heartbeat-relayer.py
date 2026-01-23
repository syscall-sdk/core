import logging
import sys
import os
import asyncio
import time
from collections import deque
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from web3 import Web3
from web3.middleware import geth_poa_middleware
from web3.exceptions import ContractLogicError, TimeExhausted
from eth_account import Account

# ==========================================
#              CONFIGURATION
# ==========================================

PORT = int(os.getenv("SYSCALL_HEARTBEAT_PORT", 8080))
RPC_URL = os.getenv("SYSCALL_HEARTBEAT_RPC_URL")
RELAYER_PRIVATE_KEY = os.getenv("SYSCALL_HEARTBEAT_RELAYER_KEY") 
FACTORY_ADDRESS = os.getenv("SYSCALL_HEARTBEAT_FACTORY_ADDRESS")

# ABIs
FACTORY_ABI = '[{"inputs":[],"name":"getJobs","outputs":[{"internalType":"address[]","name":"","type":"address[]"}],"stateMutability":"view","type":"function"}]'
JOB_ABI = '[{"inputs":[],"name":"lastRun","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"stateMutability":"view","type":"function"}, {"inputs":[],"name":"interval","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"stateMutability":"view","type":"function"}, {"inputs":[],"name":"executeTask","outputs":[],"stateMutability":"nonpayable","type":"function"}]'

# --- Logger Setup ---
if not os.path.exists("logs"): os.makedirs("logs")

# 1. In-Memory Log Buffer (Stores last 100 lines)
log_buffer = deque(maxlen=100)

class BufferHandler(logging.Handler):
    def emit(self, record):
        try:
            msg = self.format(record)
            log_buffer.append(msg)
        except Exception:
            self.handleError(record)

logger = logging.getLogger("syscall-heartbeat")
logger.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - [HEARTBEAT] - %(message)s')

# Stream Handler (Stdout/Docker)
stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setFormatter(formatter)
logger.addHandler(stream_handler)

# Buffer Handler (API)
buffer_handler = BufferHandler()
buffer_handler.setFormatter(formatter)
logger.addHandler(buffer_handler)

# Global State
w3 = None
account = None
REAL_CHAIN_ID = None

# ==========================================
#           KEEPER LOGIC (BOT)
# ==========================================

async def monitor_and_execute_jobs():
    logger.info("🤖 Keeper Bot Started...")
    
    while True:
        try:
            if not w3 or not w3.is_connected():
                logger.warning("⚠️ Web3 disconnected, retrying...")
                await asyncio.sleep(5)
                continue

            # 1. Fetch Jobs
            try:
                factory = w3.eth.contract(address=Web3.to_checksum_address(FACTORY_ADDRESS), abi=FACTORY_ABI)
                jobs = factory.functions.getJobs().call()
            except Exception as e:
                logger.error(f"Failed to fetch jobs: {e}")
                await asyncio.sleep(10)
                continue

            current_timestamp = int(time.time())

            for job_addr in jobs:
                try:
                    job_contract = w3.eth.contract(address=job_addr, abi=JOB_ABI)
                    
                    # 2. Check Conditions (Read-Only)
                    last_run = job_contract.functions.lastRun().call()
                    interval = job_contract.functions.interval().call()
                    balance = w3.eth.get_balance(job_addr)

                    next_run = last_run + interval
                    is_solvent = balance >= Web3.to_wei(0.002, 'ether')

                    if current_timestamp >= next_run and is_solvent:
                        logger.info(f"⚡ Attempting Job: {job_addr} (Interval: {interval}s)")
                        
                        tx_func = job_contract.functions.executeTask()
                        
                        # 3. Build Transaction (EIP-1559 Aggressive Strategy)
                        try:
                            latest_block = w3.eth.get_block('latest')
                            base_fee = latest_block['baseFeePerGas']
                            
                            # Priority Fee (Tip) - Increase if network is congested
                            priority_fee = w3.to_wei(2.5, 'gwei') 
                            
                            # Max Fee = (Base Fee * 2) + Tip
                            max_fee = (base_fee * 2) + priority_fee

                            tx_params = {
                                'from': account.address,
                                'nonce': w3.eth.get_transaction_count(account.address, 'pending'),
                                'chainId': REAL_CHAIN_ID,
                                'maxFeePerGas': max_fee,
                                'maxPriorityFeePerGas': priority_fee,
                                'type': 2 # Force EIP-1559
                            }

                            # Simulation
                            gas_est = tx_func.estimate_gas(tx_params)
                            tx_params['gas'] = int(gas_est * 1.5) # +50% Safety Buffer

                            # Sign
                            signed_tx = w3.eth.account.sign_transaction(tx_func.build_transaction(tx_params), RELAYER_PRIVATE_KEY)
                            
                            # Send
                            tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)
                            logger.info(f"   >>> TX Sent: {tx_hash.hex()}")
                            
                            # Wait for Confirmation (Prevents silent drops)
                            receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
                            if receipt.status == 1:
                                logger.info(f"   ✅ TX Confirmed in Block {receipt.blockNumber}")
                            else:
                                logger.error(f"   ❌ TX Reverted on-chain!")

                        except ContractLogicError as cle:
                            # Usually means another bot executed it first
                            logger.debug(f"   >>> Skipped (Race/Logic): {cle}")
                        except TimeExhausted:
                            logger.warning(f"   ⚠️ TX Timeout (Network Congested), will retry next loop.")
                        except Exception as tx_err:
                            logger.error(f"   >>> TX Failure: {tx_err}")

                except Exception as job_err:
                    pass

        except Exception as e:
            logger.error(f"Global Loop Error: {e}")
        
        # Sleep approx 1 block time
        await asyncio.sleep(10)

# ==========================================
#              LIFECYCLE
# ==========================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    global w3, account, REAL_CHAIN_ID
    try:
        w3 = Web3(Web3.HTTPProvider(RPC_URL))
        w3.middleware_onion.inject(geth_poa_middleware, layer=0) 
        
        if RELAYER_PRIVATE_KEY:
            account = Account.from_key(RELAYER_PRIVATE_KEY)
            logger.info(f"✅ Bot Wallet Loaded: {account.address}")
        
        if w3.is_connected():
            REAL_CHAIN_ID = w3.eth.chain_id
            logger.info(f"✅ Connected to RPC: {RPC_URL}")
            logger.info(f"🔗 Detected Chain ID: {REAL_CHAIN_ID}")
            asyncio.create_task(monitor_and_execute_jobs())
        else:
            logger.error(f"❌ Failed to connect to RPC")
            
    except Exception as e:
        logger.error(f"❌ Init Error: {e}")
    
    yield
    logger.info("🔌 System Shutdown.")

app = FastAPI(title="Syscall Heartbeat Relayer", version="2.2.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex="https?://.*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if not os.path.exists("static"): os.makedirs("static")
app.mount("/static", StaticFiles(directory="static"), name="static")

# ==========================================
#                ENDPOINTS
# ==========================================

@app.get("/")
async def serve_frontend():
    return FileResponse("static/index.html")

@app.get("/config")
def get_config():
    return { 
        "rpc_url": RPC_URL, 
        "factory_address": FACTORY_ADDRESS, 
        "chain_id": REAL_CHAIN_ID 
    }

@app.get("/logs")
def get_logs():
    """Returns the last 100 log lines from the in-memory buffer."""
    return list(log_buffer)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
