// app.js - Syscall SMS Service Logic

// --- DOM Elements ---
const btn = document.getElementById('executeBtn');
const targetInput = document.getElementById('targetInput');
// Removed Subject/Sender inputs as they are not used in SMS
const messageInput = document.getElementById('messageInput');
const terminal = document.getElementById('terminal');
const priceDisplay = document.getElementById('priceDisplay'); 

// --- INITIALIZATION ---
// Initialize SDK purely for read-only access first
const readOnlySyscall = new Syscall(window.ethereum);

async function initPrice() {
    try {
        // ✅ FETCH SMS PRICE
        const price = await readOnlySyscall.getServicePrice('sms');
        
        if(priceDisplay) {
            priceDisplay.innerHTML = `${price} ETH <span class="unit">/ byte</span>`;
        }
    } catch (e) {
        console.error("Price fetch failed", e);
        priceDisplay.innerText = "UNAVAILABLE";
    }
}

// Fetch price on load
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

// 💥 Console Interceptor
const originalConsoleLog = console.log;
const originalConsoleError = console.error;

console.log = function(...args) {
    originalConsoleLog.apply(console, args); 
    const text = args.map(arg => (typeof arg === 'object' ? JSON.stringify(arg) : String(arg))).join(' ');

    if (text.includes("[SDK]") || text.includes("Syscall")) {
        if (text.includes("Error")) logToTerminal(text, 'error');
        else if (text.includes("TX Sent")) logToTerminal("⚡ " + text, 'warn');
        else if (text.includes("Confirmed")) logToTerminal("✅ " + text, 'success');
        else logToTerminal(text, 'data');
    }
};

console.error = function(...args) {
    originalConsoleError.apply(console, args);
    const text = args.map(arg => String(arg)).join(' ');
    logToTerminal("❌ " + text, 'error');
};

// --- EXECUTION FLOW ---
btn.addEventListener('click', async () => {
    const destination = targetInput.value;
    const content = messageInput.value;

    if (!destination || !content) {
        logToTerminal("INPUT_ERR: Phone Number and Content are required.", "error");
        return;
    }

    if (!window.ethereum) {
        logToTerminal("CRITICAL: MetaMask (Web3 Provider) not found.", "error");
        return;
    }

    try {
        btn.disabled = true;
        btn.innerHTML = "⏳ CONNECTING TO CHAIN...";
        terminal.innerHTML = ""; 

        logToTerminal("--- INITIATING SMS PROTOCOL ---", "system");

        logToTerminal("1️⃣ Injecting Provider...", "info");
        const syscall = new Syscall(window.ethereum);

        logToTerminal(`   Target:  ${destination}`, "info");
        
        logToTerminal("2️⃣ Awaiting User Signature (Commitment)...", "warn");
        
        const startTime = Date.now();
        // ✅ CALL sendSMS INSTEAD OF sendEmail
        const result = await syscall.sendSMS(destination, content);
        const duration = ((Date.now() - startTime) / 1000).toFixed(2);

        // Result
        logToTerminal("----------------------------------", "system");
        logToTerminal(`🎉 EXECUTION SUCCESS (${duration}s)`, "success");
        logToTerminal(">> ON-CHAIN COMMITMENT:", "info");
        logToTerminal(`   TX: ${result.txHash}`, "data");
        logToTerminal(">> CRYPTOGRAPHIC REVEAL:", "info");
        // ✅ Safe Secret Display
        logToTerminal(`   Secret: ${result.secret.substring(0, 15)}...`, "data");
        logToTerminal(">> RELAYER ACKNOWLEDGMENT:", "info");
        logToTerminal(JSON.stringify(result.gatewayResult, null, 2), "data");

    } catch (error) {
        console.error(error); 
        logToTerminal("EXECUTION_ABORTED: See console.", "error");
    } finally {
        btn.disabled = false;
        btn.innerHTML = `<span class="btn-text">PAY & SEND SMS</span>`;
        logToTerminal("--- SYSTEM READY ---", "system");
    }
});
