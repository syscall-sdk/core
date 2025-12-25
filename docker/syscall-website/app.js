// app.js - Verbose Edition

// --- 1. DOM Elements ---
const btn = document.getElementById('executeBtn');
const serviceSelector = document.getElementById('serviceSelector');
const targetInput = document.getElementById('targetInput');
const targetLabel = document.getElementById('targetLabel');
const messageInput = document.getElementById('messageInput');
const terminal = document.getElementById('terminal');

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
// This allows us to see what happens INSIDE syscall-sdk.js without modifying it.
const originalConsoleLog = console.log;
const originalConsoleError = console.error;

console.log = function(...args) {
    originalConsoleLog.apply(console, args); // Keep working in browser dev tools

    // Convert arguments to a single string
    const text = args.map(arg => (typeof arg === 'object' ? JSON.stringify(arg) : String(arg))).join(' ');

    // Filter and format SDK messages
    if (text.includes("[SDK]")) {
        if (text.includes("Error")) logToTerminal(text, 'error');
        else if (text.includes("TX Sent")) logToTerminal("⛓️ " + text, 'warn'); // Highlight TX
        else if (text.includes("Confirmed")) logToTerminal("✅ " + text, 'success');
        else logToTerminal(text, 'data'); // Standard SDK logs
    }
};

console.error = function(...args) {
    originalConsoleError.apply(console, args);
    const text = args.map(arg => String(arg)).join(' ');
    logToTerminal("❌ " + text, 'error');
};


// --- 3. UI HELPER ---
serviceSelector.addEventListener('change', (e) => {
    if (e.target.value === 'sms') {
        targetLabel.innerText = "2. Target Phone Number";
        targetInput.placeholder = "+33612345678";
    } else {
        targetLabel.innerText = "2. Target Email Address";
        targetInput.placeholder = "alice@example.com";
    }
});

// --- 4. MAIN EXECUTION LOGIC ---
btn.addEventListener('click', async () => {
    // A. Validation
    const service = serviceSelector.value;
    const destination = targetInput.value;
    const content = messageInput.value;

    if (!destination || !content) {
        logToTerminal("Input Error: Please fill in all fields.", "error");
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
        terminal.innerHTML = ""; // Clear previous logs

        logToTerminal("--- STARTING NEW PROCESS ---", "info");

        // C. Init SDK
        logToTerminal("1️⃣ Initializing SDK with Browser Wallet...", "info");
        const syscall = new Syscall(window.ethereum);

        logToTerminal(`   Service: ${service.toUpperCase()}`, "info");
        logToTerminal(`   Target:  ${destination}`, "info");

        // D. Execution Flow
        logToTerminal("2️⃣ Preparing Blockchain Transaction...", "info");
        logToTerminal("   👉 PLEASE CHECK METAMASK TO CONFIRM PAYMENT", "warn");

        let result;

        // We wrap the call to catch the exact moment the promise resolves
        const startTime = Date.now();

        if (service === 'sms') {
            result = await syscall.sendSMS(destination, content);
        } else {
            result = await syscall.sendEmail(destination, content);
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
        // Pretty print JSON response
        const jsonResponse = JSON.stringify(result.gatewayResult, null, 2);
        logToTerminal(jsonResponse, "data");

    } catch (error) {
        console.error(error); // This will trigger our intercepted console.error
        logToTerminal("Process Aborted due to error.", "error");
    } finally {
        btn.disabled = false;
        btn.innerText = "PAY & EXECUTE";
        logToTerminal("--- READY FOR NEXT COMMAND ---", "info");
    }
});
