// app.js - Verbose Edition (Updated for Subject & Sender Name)

// --- 1. DOM Elements ---
const btn = document.getElementById('executeBtn');
const serviceSelector = document.getElementById('serviceSelector');
const targetInput = document.getElementById('targetInput');
const targetLabel = document.getElementById('targetLabel');
const messageInput = document.getElementById('messageInput');
const terminal = document.getElementById('terminal');

// NEW ELEMENTS
const emailFields = document.getElementById('emailFields');
const senderNameInput = document.getElementById('senderNameInput');
const subjectInput = document.getElementById('subjectInput');

// --- 2. TERMINAL & LOGGER SYSTEM ---

/**
 * Adds a line to the visual terminal.
 * @param {string} msg - The text to display
 * @param {string} type - Class name: 'info', 'success', 'error', 'data', 'warn'
 */
function logToTerminal(msg, type = 'info') {
    const div = document.createElement('div');
    div.classList.add('log-line', `log-${type}`);

    // Add Timestamp
    const now = new Date();
    const timeString = now.toLocaleTimeString('en-US', { hour12: false }) + "." + String(now.getMilliseconds()).padStart(3, '0');

    // formatting
    div.innerHTML = `<span style="opacity:0.5">[${timeString}]</span> ${msg}`;

    terminal.appendChild(div);
    terminal.scrollTop = terminal.scrollHeight; // Auto-scroll to bottom
}

// 💥 THE MAGIC TRICK: Intercept console.log from the SDK
const originalConsoleLog = console.log;
const originalConsoleError = console.error;

console.log = function(...args) {
    originalConsoleLog.apply(console, args); 

    const text = args.map(arg => (typeof arg === 'object' ? JSON.stringify(arg) : String(arg))).join(' ');

    if (text.includes("[SDK]")) {
        if (text.includes("Error")) logToTerminal(text, 'error');
        else if (text.includes("TX Sent")) logToTerminal("⛓️ " + text, 'warn');
        else if (text.includes("Confirmed")) logToTerminal("✅ " + text, 'success');
        else logToTerminal(text, 'data');
    }
};

console.error = function(...args) {
    originalConsoleError.apply(console, args);
    const text = args.map(arg => String(arg)).join(' ');
    logToTerminal("❌ " + text, 'error');
};


// --- 3. UI HELPER ---
function updateUIState() {
    const service = serviceSelector.value;
    
    if (service === 'sms') {
        targetLabel.innerText = "2. Target Phone Number";
        targetInput.placeholder = "+33612345678";
        // Hide Email fields for SMS
        emailFields.style.display = 'none';
    } else {
        targetLabel.innerText = "2. Target Email Address";
        targetInput.placeholder = "alice@example.com";
        // Show Email fields
        emailFields.style.display = 'block';
    }
}

// Init UI on load
updateUIState();

serviceSelector.addEventListener('change', updateUIState);

// --- 4. MAIN EXECUTION LOGIC ---
btn.addEventListener('click', async () => {
    // A. Validation
    const service = serviceSelector.value;
    const destination = targetInput.value;
    const content = messageInput.value;

    // Get new values
    const subject = subjectInput.value || "syscall notification"; // Default if empty
    const senderName = senderNameInput.value || "syscall-sdk"; // Default if empty

    if (!destination || !content) {
        logToTerminal("Input Error: Please fill in destination and content.", "error");
        return;
    }

    // B. Check Wallet
    if (!window.ethereum) {
        logToTerminal("System Error: MetaMask not found.", "error");
        return;
    }

    try {
        // Lock UI
        btn.disabled = true;
        btn.innerText = "⏳ EXECUTING...";
        terminal.innerHTML = ""; 

        logToTerminal("--- STARTING NEW PROCESS ---", "info");

        // C. Init SDK
        logToTerminal("1️⃣ Initializing SDK with Browser Wallet...", "info");
        const syscall = new Syscall(window.ethereum);

        logToTerminal(`   Service: ${service.toUpperCase()}`, "info");
        logToTerminal(`   Target:  ${destination}`, "info");
        
        if(service === 'email') {
            logToTerminal(`   Subject: "${subject}"`, "info");
            logToTerminal(`   Sender:  "${senderName}"`, "info");
        }

        // D. Execution Flow
        logToTerminal("2️⃣ Preparing Blockchain Transaction...", "info");
        logToTerminal("   👉 PLEASE CHECK METAMASK TO CONFIRM PAYMENT", "warn");

        let result;

        const startTime = Date.now();

        if (service === 'sms') {
            // SMS signature remains: (phone, content)
            result = await syscall.sendSMS(destination, content);
        } else {
            // Email signature updated: (email, subject, senderName, content)
            result = await syscall.sendEmail(destination, subject, senderName, content);
        }

        const duration = ((Date.now() - startTime) / 1000).toFixed(2);

        // E. Result Display
        logToTerminal("----------------------------------", "info");
        logToTerminal(`🎉 PROCESS COMPLETED in ${duration}s`, "success");

        logToTerminal("📝 TRANSACTION DETAILS:", "info");
        logToTerminal(`   Hash: ${result.txHash}`, "data");
        logToTerminal(`   Status: ${result.relayerStatus}`, "data");

        logToTerminal("🔐 SECURITY PROOF (JWT):", "info");
        logToTerminal(`   ${result.jwt.substring(0, 50)}...`, "data");

        logToTerminal("📡 GATEWAY RESPONSE:", "info");
        const jsonResponse = JSON.stringify(result.gatewayResult, null, 2);
        logToTerminal(jsonResponse, "data");

    } catch (error) {
        console.error(error); 
        logToTerminal("Process Aborted due to error.", "error");
    } finally {
        btn.disabled = false;
        btn.innerText = "PAY & EXECUTE";
        logToTerminal("--- READY FOR NEXT COMMAND ---", "info");
    }
});
