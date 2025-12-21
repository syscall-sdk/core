const readline = require('readline');
const Syscall = require('./syscall-sdk'); 
require('dotenv').config(); 

const rl = readline.createInterface({
    input: process.stdin, output: process.stdout
});

const askQuestion = (query) => new Promise((resolve) => rl.question(query, resolve));

async function main() {
    console.clear();
    console.log("==========================================");
    console.log("      SYSCALL SDK - CLI TESTER            ");
    console.log("==========================================\n");

    try {
        // --- 1. Get Private Key ---
        let privateKey = process.env.PRIVATE_KEY;
        if (!privateKey) {
            privateKey = await askQuestion("Enter Wallet Private Key: ");
        } else {
            // [RESTORED] Visual style from screenshot
            console.log("✅ Using Private Key from .env");
        }

        console.log("[1/4] Initializing SDK...");
        const syscall = new Syscall(privateKey);

        // --- 2. Select Service & Prepare Details ---
        console.log("\n[2/4] Preparing Transaction Details:");
        
        console.log("Select Service:");
        console.log("   1. Send SMS");
        console.log("   2. Send Email");
        const choice = await askQuestion("   > Choice (1 or 2): ");

        let result;
        
        if (choice === '1') {
            // SMS Logic
            let phoneNumber = process.env.TEST_PHONE;
            if (phoneNumber) {
                console.log(`✅ Using Phone from .env: ${phoneNumber}`);
            } else {
                phoneNumber = await askQuestion("Target Phone Number: ");
            }

            let message = process.env.TEST_MESSAGE;
            if (message) {
                console.log(`✅ Using Message from .env: "${message}"`);
            } else {
                message = await askQuestion("Message Content: ");
            }

            console.log("\n[3/4] Processing Payment & Action...");
            console.log("------------------------------------------");
            result = await syscall.sendSMS(phoneNumber, message);

        } else if (choice === '2') {
            // Email Logic
            let email = process.env.TEST_EMAIL;
            if (email) {
                console.log(`✅ Using Email from .env: ${email}`);
            } else {
                email = await askQuestion("Target Email Address: ");
            }

            let message = process.env.TEST_MESSAGE;
            if (message) {
                console.log(`✅ Using Message from .env: "${message}"`);
            } else {
                message = await askQuestion("Message Content: ");
            }

            console.log("\n[3/4] Processing Payment & Action...");
            console.log("------------------------------------------");
            result = await syscall.sendEmail(email, message);

        } else {
            throw new Error("Invalid choice.");
        }

        // --- Success Output ---
        console.log("------------------------------------------");
        console.log("\n[4/4] SUCCESS! 🚀");
        console.log(`Transaction Hash: ${result.txHash}`);
        
        // [NEW] Display Relayer Info cleanly
        console.log(`Relayer Status:   ${result.relayerStatus.toUpperCase()}`);
        console.log(`JWT Token:        ${result.jwt ? "Received (Authorized)" : "None"}`);
        
    } catch (error) {
        console.error("\n❌ ERROR:", error.message || error);
    } finally {
        rl.close();
        process.exit(0);
    }
}

main();
