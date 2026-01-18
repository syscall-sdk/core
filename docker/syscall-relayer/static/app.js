// app.js - Syscall SDK Interface Logic

// --- 1. DOM Elements ---
const btn = document.getElementById('executeBtn');
const serviceSelector = document.getElementById('serviceSelector');
const targetInput = document.getElementById('targetInput');
const targetLabel = document.getElementById('targetLabel');
const messageInput = document.getElementById('messageInput');
const terminal = document.getElementById('terminal');

// Extended Fields
const emailFields = document.getElementById('emailFields');
const senderNameInput = document.getElementById('senderNameInput');
const subjectInput = document.getElementById('subjectInput');

// --- 2. TERMINAL & LOGGER SYSTEM ---
/**
 * Renders logs to the custom HTML terminal
 */
function logToTerminal(msg, type = 'info') {
    const div = document.createElement('div');
    div.classList.add('log-line', `log-${type}`);

    const now = new Date();
    const timeString = now.toLocaleTimeString('en-US', { hour12: false }) + "." + String(now.getMilliseconds()).padStart(3, '0');

    div.innerHTML = `<span style="opacity:0.4; font-size:0.8em">[${timeString}]</span> ${msg}`;

    terminal.appendChild(div);
    terminal.scrollTop = terminal.scrollHeight;
}

// 💥 THE MAGIC TRICK: Intercept SDK Console Output
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
    } else {
        // Log other standard messages delicately
        // logToTerminal(text, 'info'); 
    }
};

console.error = function(...args) {
    originalConsoleError.apply(console, args);
    const text = args.map(arg => String(arg)).join(' ');
    logToTerminal("❌ " + text, 'error');
};

// --- 3. UI STATE MANAGEMENT ---
function updateUIState() {
    const service = serviceSelector.value;
    
    if (service === 'sms') {
        targetLabel.innerText = "2. TARGET PHONE NUMBER";
        targetInput.placeholder = "+33612345678";
        emailFields.style.display = 'none';
    } else {
        targetLabel.innerText = "2. TARGET EMAIL ADDRESS";
        targetInput.placeholder = "alice@example.com";
        emailFields.style.display = 'block';
    }
}

// Initialization
updateUIState();
serviceSelector.addEventListener('change', updateUIState);

// --- 4. EXECUTION FLOW ---
btn.addEventListener('click', async () => {
    // A. Validation
    const service = serviceSelector.value;
    const destination = targetInput.value;
    const content = messageInput.value;
    const subject = subjectInput.value || "syscall notification";
    const senderName = senderNameInput.value || "syscall-sdk";

    if (!destination || !content) {
        logToTerminal("INPUT_ERR: Destination and Content are required.", "error");
        return;
    }

    // B. Wallet Check
    if (!window.ethereum) {
        logToTerminal("CRITICAL: MetaMask (Web3 Provider) not found.", "error");
        return;
    }

    try {
        // Lock UI
        btn.disabled = true;
        btn.innerHTML = "⏳ PROCESSING CHAIN REQUEST...";
        terminal.innerHTML = ""; 

        logToTerminal("--- INITIATING SYSCALL PROTOCOL ---", "system");

        // C. SDK Initialization
        logToTerminal("1️⃣ Injecting Provider...", "info");
        // NOTE: Assumes Syscall class is globally available via syscall-sdk.js
        const syscall = new Syscall(window.ethereum);

        logToTerminal(`   Mode:    ${service.toUpperCase()}`, "info");
        logToTerminal(`   Target:  ${destination}`, "info");
        
        if(service === 'email') {
            logToTerminal(`   Header:  "${subject}"`, "info");
            logToTerminal(`   From:    "${senderName}"`, "info");
        }

        // D. Transaction
        logToTerminal("2️⃣ Awaiting User Signature...", "warn");
        
        const startTime = Date.now();
        let result;

        if (service === 'sms') {
            result = await syscall.sendSMS(destination, content);
        } else {
            result = await syscall.sendEmail(destination, subject, senderName, content);
        }

        const duration = ((Date.now() - startTime) / 1000).toFixed(2);

        // E. Result Handling
        logToTerminal("----------------------------------", "system");
        logToTerminal(`🎉 EXECUTION SUCCESS (${duration}s)`, "success");

        logToTerminal(">> ON-CHAIN PROOF:", "info");
        logToTerminal(`   TX: ${result.txHash}`, "data");
        
        logToTerminal(">> OFF-CHAIN RELAY:", "info");
        logToTerminal(`   JWT: ${result.jwt.substring(0, 20)}...[REDACTED]`, "data");

        logToTerminal(">> GATEWAY RESPONSE:", "info");
        logToTerminal(JSON.stringify(result.gatewayResult, null, 2), "data");

    } catch (error) {
        console.error(error); 
        logToTerminal("EXECUTION_ABORTED: See console for stack trace.", "error");
    } finally {
        btn.disabled = false;
        btn.innerHTML = `<span class="btn-text">INITIALIZE TRANSACTION</span>`;
        logToTerminal("--- SYSTEM READY ---", "system");
    }
});


