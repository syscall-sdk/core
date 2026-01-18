// app.js - Syscall SMS Service Logic (Strict Mode)

const CHAIN_NAME = "Syscall Network";       

// --- DOM Elements ---
const btn = document.getElementById('executeBtn');
const targetInput = document.getElementById('targetInput');
const messageInput = document.getElementById('messageInput');
const terminal = document.getElementById('terminal');
const priceDisplay = document.getElementById('priceDisplay'); 

// --- INITIALIZATION ---
// Initialize SDK purely for read-only access first
const readOnlySyscall = new Syscall(window.ethereum);

async function initPrice() {
    try {
        const price = await readOnlySyscall.getServicePrice('sms');
        if(priceDisplay) {
            priceDisplay.innerHTML = `${price} ETH <span class="unit">/ byte</span>`;
        }
    } catch (e) {
        console.error("Price fetch failed", e);
        priceDisplay.innerText = "UNAVAILABLE";
    }
}

initPrice();

// --- LOGGER SYSTEM ---
function logToTerminal(msg, type = 'info') {
    const div = document.createElement('div');
    div.classList.add('log-line', `log-${type}`);
    const now = new Date();
    const timeString = now.toLocaleTimeString('en-US', { hour12: false }) + "." + String(now.getMilliseconds()).padStart(3, '0');
    div.innerHTML = `<span style="opacity:0.4; font-size:0.8em">[${timeString}]</span> ${msg}`;
    terminal.appendChild(div);
    terminal.scrollTop = terminal.scrollHeight;
}

// ============================================================
// 🔄 NETWORK SWITCHER (FULLY DYNAMIC)
// ============================================================
async function switchToTargetNetwork(dynamicRpcUrl, dynamicChainIdHex) {
    try {
        logToTerminal(`🔄 Requesting Switch to Chain ${dynamicChainIdHex}...`, "system");
        
        await window.ethereum.request({
            method: 'wallet_switchEthereumChain',
            params: [{ chainId: dynamicChainIdHex }],
        });
        
        return true;

    } catch (switchError) {
        // Error 4902: Network not found -> Add it
        if (switchError.code === 4902) {
            logToTerminal("➕ Network not found. Adding it...", "warn");
            
            if (!dynamicRpcUrl) throw new Error("RPC URL missing from SDK config.");

            try {
                await window.ethereum.request({
                    method: 'wallet_addEthereumChain',
                    params: [
                        {
                            chainId: dynamicChainIdHex,
                            chainName: CHAIN_NAME,
                            rpcUrls: [dynamicRpcUrl],
                            nativeCurrency: { name: "ETH", symbol: "ETH", decimals: 18 },
                        },
                    ],
                });
                return true;
            } catch (addError) {
                logToTerminal("❌ Failed to add network.", "error");
                throw addError;
            }
        } else {
            logToTerminal("❌ User rejected network switch.", "error");
            throw switchError;
        }
    }
}

// ============================================================
// 🛡️ SECURITY & DIAGNOSTICS (STRICT)
// ============================================================
async function runDiagnostics(initialProvider) {
    logToTerminal("🔍 Running Pre-Flight Checks...", "system");

    let currentProvider = initialProvider;

    if (!window.ethereum) throw new Error("MetaMask/Web3 Wallet not found.");

    // 1. Config Check (Load from Relayer via SDK)
    try {
        await readOnlySyscall._fetchConfig(); 
    } catch (e) {
        throw new Error("CRITICAL: Failed to load config from Relayer. Is the Relayer online?");
    }
    
    const config = readOnlySyscall.config;

    // [STRICT] Check for ChainID existence. NO DEFAULT allowed.
    if (!config || !config.rpc_url || !config.contract_address || !config.chain_id) {
        throw new Error("Configuration Error: Missing parameters from Relayer (RPC/Address/ChainID).");
    }
    
    const rpcUrl = config.rpc_url;
    const contractAddress = config.contract_address;
    
    // Dynamic Chain Parsing
    const targetChainId = BigInt(config.chain_id);
    const targetChainIdHex = "0x" + config.chain_id.toString(16);

    logToTerminal(`   Relayer RPC: ${rpcUrl}`, "data");
    logToTerminal(`   Target Chain: ${targetChainId}`, "data");

    // 2. Network Check
    const network = await currentProvider.getNetwork();
    logToTerminal(`   Current Chain ID: ${network.chainId}`, "data");
    
    // Auto-Switch Logic
    if (network.chainId !== targetChainId) {
        logToTerminal(`⚠️ Wrong Network. Switching to ${targetChainId}...`, "warn");
        
        await switchToTargetNetwork(rpcUrl, targetChainIdHex);
        
        // --- CRITICAL REFRESH ---
        await new Promise(r => setTimeout(r, 1000));
        currentProvider = new ethers.BrowserProvider(window.ethereum); 
        
        const newNetwork = await currentProvider.getNetwork();
        if (newNetwork.chainId !== targetChainId) {
            throw new Error(`Network switch failed. Stuck on ${newNetwork.chainId}.`);
        }
        logToTerminal("✅ Network Switched Successfully.", "success");
    }

    // 3. Contract Existence Check
    const code = await currentProvider.getCode(contractAddress);
    if (code === "0x") {
        throw new Error(`CRITICAL: No Smart Contract found at ${contractAddress}`);
    }

    // 4. Balance Check
    const signer = await currentProvider.getSigner();
    const address = await signer.getAddress();
    const balance = await currentProvider.getBalance(address);
    
    if (balance === 0n) {
        logToTerminal("⚠️ WARNING: Wallet balance is 0 ETH.", "warn");
    } else {
        logToTerminal("✅ Wallet Funded & Ready.", "success");
    }

    return true;
}

// --- EXECUTION FLOW ---
btn.addEventListener('click', async () => {
    const destination = targetInput.value;
    const content = messageInput.value;

    if (!destination || !content) {
        logToTerminal("INPUT_ERR: Phone Number and Content are required.", "error");
        return;
    }

    try {
        btn.disabled = true;
        btn.innerHTML = "⏳ DIAGNOSTICS..."; 
        terminal.innerHTML = ""; 

        const provider = new ethers.BrowserProvider(window.ethereum);
        
        await runDiagnostics(provider);

        logToTerminal("--- INITIATING SMS PROTOCOL ---", "system");
        
        logToTerminal("1️⃣ Injecting Provider...", "info");
        const syscall = new Syscall(window.ethereum);

        logToTerminal(`   Target:  ${destination}`, "info");
        logToTerminal("2️⃣ Awaiting User Signature...", "warn");
        
        const startTime = Date.now();
        
        const result = await syscall.sendSMS(destination, content);
        const duration = ((Date.now() - startTime) / 1000).toFixed(2);

        logToTerminal("----------------------------------", "system");
        logToTerminal(`🎉 EXECUTION SUCCESS (${duration}s)`, "success");
        logToTerminal(">> ON-CHAIN COMMITMENT:", "info");
        logToTerminal(`   TX: ${result.txHash}`, "data");
        logToTerminal(">> CRYPTOGRAPHIC REVEAL:", "info");
        
        if (result.secret) {
            logToTerminal(`   Secret: ${result.secret.substring(0, 15)}...`, "data");
        }
        
        logToTerminal(">> RELAYER ACKNOWLEDGMENT:", "info");
        logToTerminal(JSON.stringify(result.gatewayResult, null, 2), "data");

    } catch (error) {
        console.error(error);
        
        if (error.code === "NETWORK_ERROR") {
             logToTerminal("⚠️ Network Changed. Please click again.", "warn");
             btn.innerHTML = "RETRY";
        } else {
             const errMsg = error.reason || error.message || "Unknown Error";
             logToTerminal(`❌ ABORTED: ${errMsg}`, "error");
        }
    } finally {
        btn.disabled = false;
        if(btn.innerHTML !== "RETRY") {
             btn.innerHTML = `<span class="btn-text">PAY & SEND SMS</span>`;
        }
        logToTerminal("--- SYSTEM READY ---", "system");
    }
});
