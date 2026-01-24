
// app.js - Syscall Heartbeat Frontend Logic (Strict Mode)
// Relies on global SyscallHeartbeat class from SDK

const CHAIN_NAME = "Syscall Network";

// --- DOM ELEMENTS ---
const btn = document.getElementById('executeBtn');
const targetInput = document.getElementById('targetInput');
const funcSigInput = document.getElementById('funcSigInput');
const funcArgsInput = document.getElementById('funcArgsInput');
const intervalInput = document.getElementById('intervalInput');
const depositInput = document.getElementById('depositInput');
const terminal = document.getElementById('terminal');
const factoryDisplay = document.getElementById('factoryDisplay');

// Explorer Elements
const jobsContainer = document.getElementById('jobsListContainer');
const searchInput = document.getElementById('searchInput');
const refreshBtn = document.getElementById('refreshBtn');
const liveFeedContainer = document.getElementById('liveFeedContainer');

let allJobsData = [];

// --- UTILS ---
function logToTerminal(msg, type = 'info') {
    const div = document.createElement('div');
    div.classList.add('log-line', `log-${type}`);
    const timeString = new Date().toLocaleTimeString('en-US', { hour12: false });
    div.innerHTML = `<span style="opacity:0.4; font-size:0.8em">[${timeString}]</span> ${msg}`;
    terminal.appendChild(div);
    terminal.scrollTop = terminal.scrollHeight;
}

// --- INITIALIZATION ---
let sdk;
try {
    if (typeof SyscallHeartbeat !== 'undefined') {
        sdk = new SyscallHeartbeat(window.ethereum);
    } else {
        throw new Error("SyscallHeartbeat Class is missing. Check sdk.js");
    }
} catch (e) {
    console.error("SDK Init Error:", e);
}

// Read-Only Init for Explorer and Feed
async function initUI() {
    if (!sdk) {
        logToTerminal("❌ FATAL: SDK failed to load.", "error");
        return;
    }
    try {
        await sdk._fetchConfig();
        if(factoryDisplay && sdk.config) {
            factoryDisplay.innerText = sdk.config.factory_address;
            logToTerminal(`System Online. Chain ID: ${sdk.config.chain_id}`, "system");
            
            // Load Passive components
            fetchAndRenderJobs();
            startLiveFeed();
        }
    } catch(e) {
        console.error(e);
        logToTerminal("⚠️ Relayer Connection Failed.", "error");
        jobsContainer.innerHTML = `<div class="log-error">Failed to connect to Relayer.</div>`;
    }
}
initUI();

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

    // 1. Config Check
    try { await sdk._fetchConfig(); } 
    catch (e) { throw new Error("CRITICAL: Failed to load config from Relayer."); }
    
    const config = sdk.config;
    if (!config || !config.rpc_url || !config.factory_address || !config.chain_id) {
        throw new Error("Configuration Error: Missing parameters.");
    }

    const rpcUrl = config.rpc_url;
    const factoryAddress = config.factory_address;
    const targetChainId = BigInt(config.chain_id);
    const targetChainIdHex = "0x" + config.chain_id.toString(16);

    logToTerminal(`   Relayer RPC: ${rpcUrl}`, "data");
    logToTerminal(`   Target Chain: ${targetChainId}`, "data");

    // 2. Network Check
    const network = await currentProvider.getNetwork();
    if (network.chainId !== targetChainId) {
        logToTerminal(`⚠️ Wrong Network. Switching to ${targetChainId}...`, "warn");
        await switchToTargetNetwork(rpcUrl, targetChainIdHex);
        
        // Critical Refresh
        await new Promise(r => setTimeout(r, 1000));
        currentProvider = new ethers.BrowserProvider(window.ethereum);
        const newNetwork = await currentProvider.getNetwork();
        if (newNetwork.chainId !== targetChainId) {
            throw new Error(`Network switch failed. Stuck on ${newNetwork.chainId}.`);
        }
        logToTerminal("✅ Network Switched Successfully.", "success");
    }

    // 3. Contract Check
    const code = await currentProvider.getCode(factoryAddress);
    if (code === "0x") throw new Error(`CRITICAL: No Factory found at ${factoryAddress}`);

    logToTerminal("✅ System Ready.", "success");
    return true;
}

// --- LIVE FEED LOGIC ---
async function startLiveFeed() {
    logToTerminal("📡 Connecting to Live Feed...", "system");
    setInterval(async () => {
        if (!sdk) return;
        try {
            const logs = await sdk.getRelayerLogs();
            if (logs && logs.length > 0) renderFeed(logs);
        } catch(e) {}
    }, 2000);
}

function renderFeed(logs) {
    let html = "";
    logs.forEach(line => {
        let cssClass = "feed-val";
        if (line.includes("✅")) cssClass = "feed-success";
        if (line.includes("❌") || line.includes("Error")) cssClass = "feed-error";
        if (line.includes("⚡")) cssClass = "feed-warn";
        if (line.includes(">>>")) cssClass = "highlight";

        const parts = line.split(" - ");
        const ts = parts[0] || "";
        const msg = parts.slice(2).join(" - ") || parts[1] || line;

        html += `<div class="feed-line">
            <span class="feed-ts">${ts}</span>
            <span class="${cssClass}">${msg}</span>
        </div>`;
    });
    const isAtBottom = liveFeedContainer.scrollHeight - liveFeedContainer.scrollTop === liveFeedContainer.clientHeight;
    liveFeedContainer.innerHTML = html;
    liveFeedContainer.scrollTop = liveFeedContainer.scrollHeight;
}

// --- JOB EXPLORER ---
function parseCalldata(hexData) {
    if (!hexData || hexData === "0x") return { func: "receive()", args: "-" };
    const selector = hexData.substring(0, 10); 
    const args = hexData.substring(10);
    return { func: selector, args: args ? "0x" + args : "(No Args)" };
}

async function fetchAndRenderJobs() {
    if (!sdk) return;
    jobsContainer.innerHTML = `<div class="text-content" style="text-align:center;">Fetching Registry...</div>`;
    try {
        const jobAddresses = await sdk.getJobsList();
        if (jobAddresses.length === 0) {
            jobsContainer.innerHTML = `<div class="text-content" style="text-align:center;">No Jobs found.</div>`;
            return;
        }
        jobsContainer.innerHTML = `<div class="text-content" style="text-align:center;">Loading ${jobAddresses.length} jobs...</div>`;
        const promises = jobAddresses.map(addr => sdk.getJobDetails(addr));
        const jobs = await Promise.all(promises);
        allJobsData = jobs.filter(j => j !== null);
        allJobsData.reverse(); 
        renderJobs(allJobsData);
    } catch (e) {
        console.error(e);
        jobsContainer.innerHTML = `<div class="log-error">Error: ${e.message}</div>`;
    }
}

function renderJobs(jobs) {
    if (jobs.length === 0) {
        jobsContainer.innerHTML = `<div class="text-content">No matching jobs.</div>`;
        return;
    }
    let html = "";
    jobs.forEach(job => {
        const { func, args } = parseCalldata(job.data);
        const balanceClass = parseFloat(job.balance) < 0.002 ? "log-error" : "log-success";
        html += `
        <div class="job-item">
            <div class="job-row"><span class="job-label">JOB:</span><span class="job-val highlight">${job.address}</span></div>
            <div class="job-row"><span class="job-label">TARGET:</span><span class="job-val">${job.target}</span></div>
            <div class="job-row"><span class="job-label">INTERVAL:</span><span class="job-val">${job.interval}s</span></div>
            <div class="job-row"><span class="job-label">CREDIT:</span><span class="job-val ${balanceClass}">${job.balance} ETH</span></div>
            <div style="margin-top:8px; border-top:1px solid #333; padding-top:5px;">
                <div class="job-row"><span class="job-label">FUNC:</span><span class="job-val">${func}</span></div>
                <div class="job-data" style="margin-top:2px; font-size:0.7rem; color:#666;">ARGS: ${args.length > 50 ? args.substring(0, 50) + "..." : args}</div>
            </div>
            <div class="job-actions">
                <button class="btn-mini btn-add" data-action="topup" data-addr="${job.address}">+ ADD GAS</button>
                <button class="btn-mini btn-del" data-action="delete" data-addr="${job.address}">DELETE</button>
            </div>
        </div>`;
    });
    jobsContainer.innerHTML = html;
    
    // Bind Action Buttons
    document.querySelectorAll('.btn-add').forEach(b => {
        b.addEventListener('click', async (e) => {
            const addr = e.target.getAttribute('data-addr');
            const amount = prompt("Amount of ETH to add:", "0.01");
            if(amount) await handleTopUp(addr, amount);
        });
    });
    document.querySelectorAll('.btn-del').forEach(b => {
        b.addEventListener('click', async (e) => {
            const addr = e.target.getAttribute('data-addr');
            if(confirm(`Delete job ${addr}?`)) await handleDelete(addr);
        });
    });
}

// --- ACTION HANDLERS ---
async function handleTopUp(address, amount) {
    try {
        logToTerminal(`⛽ Topping up ${address}...`, "system");
        await runDiagnostics(new ethers.BrowserProvider(window.ethereum)); 
        const tx = await sdk.topUpJob(address, amount);
        logToTerminal(`✅ Top Up Successful!`, "success");
        setTimeout(fetchAndRenderJobs, 1000);
    } catch(e) { logToTerminal(`❌ Top Up Failed: ${e.message}`, "error"); }
}

async function handleDelete(address) {
    try {
        logToTerminal(`🗑️ Deleting ${address}...`, "system");
        await runDiagnostics(new ethers.BrowserProvider(window.ethereum)); 
        await sdk.cancelJob(address);
        logToTerminal(`✅ Job Deleted.`, "success");
        setTimeout(fetchAndRenderJobs, 2000); 
    } catch(e) { logToTerminal(`❌ Delete Failed: ${e.message}`, "error"); }
}

searchInput.addEventListener('input', (e) => {
    const query = e.target.value.toLowerCase().trim();
    if (!query) { renderJobs(allJobsData); return; }
    renderJobs(allJobsData.filter(job => job.address.toLowerCase().includes(query) || job.target.toLowerCase().includes(query)));
});
if(refreshBtn) refreshBtn.addEventListener('click', fetchAndRenderJobs);

// --- DEPLOY LOGIC ---
if (btn) {
    btn.addEventListener('click', async () => {
        const target = targetInput.value.trim();
        const sig = funcSigInput.value.trim();
        const args = funcArgsInput.value.trim();
        const interval = intervalInput.value;
        const deposit = depositInput.value;

        if (!target || !interval || !deposit) {
            logToTerminal("ERR: Missing required fields.", "error");
            return;
        }

        try {
            btn.disabled = true;
            btn.innerHTML = "⏳ DIAGNOSTICS...";
            terminal.innerHTML = ""; 
            
            // 1. Run Diagnostics (Switch network if needed)
            const provider = new ethers.BrowserProvider(window.ethereum);
            await runDiagnostics(provider);

            logToTerminal("⚙️ Encoding Calldata...", "system");
            const calldata = sdk.encodeCalldata(sig, args);
            
            logToTerminal("--- INITIATING DEPLOYMENT ---", "system");
            btn.innerHTML = "🖊️ SIGNING TX...";

            // 2. Execute Deploy
            const result = await sdk.deployJob(target, calldata, interval, deposit);

            logToTerminal(`🚀 TX Sent: ${result.txHash}`, "data");
            btn.innerHTML = "⛓️ CONFIRMING...";
            logToTerminal("✅ JOB DEPLOYED SUCCESSFULLY", "success");
            
            if (result.jobAddress) {
                logToTerminal(`   Job Address: ${result.jobAddress}`, "success");
                setTimeout(fetchAndRenderJobs, 2000);
            }

        } catch (error) {
            console.error(error);
            const errMsg = error.reason || error.message || "Unknown error";
            logToTerminal(`❌ FAILED: ${errMsg}`, "error");
        } finally {
            btn.disabled = false;
            btn.innerHTML = `<span class="btn-text">DEPLOY HEARTBEAT JOB</span>`;
        }
    });
}
