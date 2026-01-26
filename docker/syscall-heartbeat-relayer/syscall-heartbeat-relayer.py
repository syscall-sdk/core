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

# Note: Using the 5-return values ABI as requested previously
FACTORY_ABI = '[{"inputs":[],"name":"getJobs","outputs":[{"internalType":"address[]","name":"","type":"address[]"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"getGasSettings","outputs":[{"internalType":"uint256","name":"","type":"uint256"},{"internalType":"uint256","name":"","type":"uint256"},{"internalType":"uint256","name":"","type":"uint256"},{"internalType":"uint256","name":"","type":"uint256"},{"internalType":"uint256","name":"","type":"uint256"}],"stateMutability":"view","type":"function"}]'

JOB_ABI = '[{"inputs":[],"name":"lastRun","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"stateMutability":"view","type":"function"}, {"inputs":[],"name":"interval","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"stateMutability":"view","type":"function"}, {"inputs":[],"name":"executeTask","outputs":[],"stateMutability":"nonpayable","type":"function"}]'

if not os.path.exists("logs"): os.makedirs("logs")

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

stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setFormatter(formatter)
logger.addHandler(stream_handler)

buffer_handler = BufferHandler()
buffer_handler.setFormatter(formatter)
logger.addHandler(buffer_handler)

w3 = None
account = None
REAL_CHAIN_ID = None

# ==========================================
#           KEEPER LOGIC (BOT)
# ==========================================

async def monitor_and_execute_jobs():
    global REAL_CHAIN_ID
    logger.info("🤖 Keeper Bot Started... (Auto-Sync Mode)")
    
    while True:
        try:
            # 1. Connection Check & Recovery
            if not w3 or not w3.is_connected():
                logger.warning("⚠️ Web3 disconnected/unavailable, retrying in 10s...")
                await asyncio.sleep(10)
                continue

            # 2. Lazy Chain ID Fetch (if missed at startup)
            if REAL_CHAIN_ID is None:
                try:
                    REAL_CHAIN_ID = w3.eth.chain_id
                    logger.info(f"🔗 Late Connection - Chain ID Detected: {REAL_CHAIN_ID}")
                except Exception:
                    logger.error("❌ Connected but failed to fetch Chain ID")
                    await asyncio.sleep(10)
                    continue

            try:
                factory_contract = w3.eth.contract(address=Web3.to_checksum_address(FACTORY_ADDRESS), abi=FACTORY_ABI)
                jobs = factory_contract.functions.getJobs().call()
                
                # Fetch global gas settings (5 values now)
                overhead_gas, relayer_fee_gas, factory_fee_gas, solvency_threshold_gas, _ = factory_contract.functions.getGasSettings().call()
                
            except Exception as e:
                logger.error(f"Failed to fetch jobs or settings: {e}")
                await asyncio.sleep(30)
                continue

            current_timestamp = int(time.time())

            for job_addr in jobs:
                try:
                    job_contract = w3.eth.contract(address=job_addr, abi=JOB_ABI)
                    last_run = job_contract.functions.lastRun().call()
                    interval = job_contract.functions.interval().call()
                    
                    next_run = last_run + interval
            
                    if current_timestamp >= next_run:
                        # 1. Fetch Basic Data
                        balance_wei = w3.eth.get_balance(job_addr)
                        balance_eth = w3.from_wei(balance_wei, 'ether')
                        gas_price = w3.eth.gas_price
                        
                        # 2. Calculate Display Metrics
                        gas_price_gwei = w3.from_wei(gas_price, 'gwei')
                        
                        # Gas Runway
                        gas_runway_units = int(balance_wei / gas_price) if gas_price > 0 else 0
                        
                        # 3. Log PRE-EXECUTION Stats
                        logger.info(f"⚡ Attempting Job: {job_addr} (Interval: {interval}s)")
                        logger.info(f"   ⛽ Gas Price: {gas_price_gwei} Gwei")
                        logger.info(f"   💰 Balance: {balance_eth} ETH")
                        logger.info(f"   🔋 Gas Runway: ~{gas_runway_units} units")
 
                        tx_func = job_contract.functions.executeTask()
                        
                        try:
                            latest_block = w3.eth.get_block('latest')
                            base_fee = latest_block['baseFeePerGas']
                            priority_fee = w3.eth.max_priority_fee
                          
                            if priority_fee == 0:
                                priority_fee = w3.to_wei(0.01, 'gwei') 

                            max_fee = (base_fee * 2) + priority_fee

                            tx_params = {
                                'from': account.address,
                                'nonce': w3.eth.get_transaction_count(account.address, 'pending'),
                                'chainId': REAL_CHAIN_ID,
                                'maxFeePerGas': max_fee,
                                'maxPriorityFeePerGas': priority_fee,
                                'type': 2 
                            }

                            gas_est = tx_func.estimate_gas(tx_params)
                            tx_params['gas'] = int(gas_est * 1.5) 

                            signed_tx = w3.eth.account.sign_transaction(tx_func.build_transaction(tx_params), RELAYER_PRIVATE_KEY)
                            tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)
                            logger.info(f"   >>> TX Sent: {tx_hash.hex()}")
                            
                            receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
                            
                            if receipt.status == 1:
                                # 4. Log POST-EXECUTION Stats
                                gas_used = receipt['gasUsed']
                                effective_gas_price = receipt.get('effectiveGasPrice', gas_price)
                                cost_wei = gas_used * effective_gas_price
                                cost_eth = w3.from_wei(cost_wei, 'ether')
                                
                                # Projection logic
                                job_total_gas_load = gas_used + overhead_gas + relayer_fee_gas + factory_fee_gas
                                job_estimated_cost_wei = job_total_gas_load * effective_gas_price
                                
                                estimated_remaining_balance_wei = balance_wei - job_estimated_cost_wei
                                
                                runs_left = 0
                                if job_estimated_cost_wei > 0 and estimated_remaining_balance_wei > 0:
                                    runs_left = int(estimated_remaining_balance_wei / job_estimated_cost_wei)

                                logger.info(f"   ✅ TX Confirmed")
                                logger.info(f"   📉 Gas Consumed: {gas_used} units")
                                logger.info(f"   💸 Execution Cost: {cost_eth} ETH")
                                logger.info(f"   🔄 Projected Runs Left: ~{runs_left}")
                            else:
                                logger.error(f"   ❌ TX Reverted on-chain!")

                        except ContractLogicError as cle:
                            logger.debug(f"   >>> Skipped (Race/Logic): {cle}")
                        except TimeExhausted:
                            logger.warning(f"   ⚠️ TX Timeout (Network Congested)")
                        except Exception as tx_err:
                            logger.error(f"   >>> TX Failure: {tx_err}")

                except Exception as job_err:
                    pass

        except Exception as e:
            logger.error(f"Global Loop Error: {e}")
            await asyncio.sleep(10)
        
        await asyncio.sleep(30)

# ==========================================
#              LIFECYCLE
# ==========================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    global w3, account, REAL_CHAIN_ID
    try:
        # Initialize Web3 object (does not connect yet)
        w3 = Web3(Web3.HTTPProvider(RPC_URL))
        w3.middleware_onion.inject(geth_poa_middleware, layer=0) 
        
        if RELAYER_PRIVATE_KEY:
            account = Account.from_key(RELAYER_PRIVATE_KEY)
            logger.info(f"✅ Bot Wallet Loaded: {account.address}")
        
        # Check connection immediately for logging, but don't block
        if w3.is_connected():
            REAL_CHAIN_ID = w3.eth.chain_id
            logger.info(f"✅ Connected to RPC: {RPC_URL}")
            logger.info(f"🔗 Detected Chain ID: {REAL_CHAIN_ID}")
        else:
            logger.warning(f"⚠️ Initial RPC connection failed. Will retry in background task.")
            
    except Exception as e:
        logger.error(f"❌ Init Error: {e}")
    
    # ALWAYS start the background task
    asyncio.create_task(monitor_and_execute_jobs())
    
    yield
    logger.info("🔌 System Shutdown.")

app = FastAPI(title="Syscall Heartbeat Relayer", version="2.3.1", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex="https?://.*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if not os.path.exists("static"): os.makedirs("static")
app.mount("/static", StaticFiles(directory="static"), name="static")

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
    return list(log_buffer)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
