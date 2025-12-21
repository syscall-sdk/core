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
        let privateKey = process.env.PRIVATE_KEY;
        if (!privateKey) {
            privateKey = await askQuestion("Enter Wallet Private Key: ");
        } else {
            console.log("✅ Using Private Key from .env");
        }

        console.log("[1/4] Initializing SDK...");
        const syscall = new Syscall(privateKey);

        console.log("\n[2/4] Preparing Transaction Details:");
        console.log("Select Service:");
        console.log("   1. Send SMS");
        console.log("   2. Send Email");
        const choice = await askQuestion("   > Choice (1 or 2): ");

        let result;
        
        if (choice === '1') {
            let phoneNumber = process.env.TEST_PHONE || await askQuestion("Target Phone Number: ");
            let message = process.env.TEST_MESSAGE || await askQuestion("Message Content: ");
            
            console.log(`✅ Using Phone: ${phoneNumber}`);
            console.log(`✅ Using Message: "${message}"`);
            
            console.log("\n[3/4] Processing Payment & Action...");
            console.log("------------------------------------------");
            result = await syscall.sendSMS(phoneNumber, message);

        } else if (choice === '2') {
            let email = process.env.TEST_EMAIL || await askQuestion("Target Email Address: ");
            let message = process.env.TEST_MESSAGE || await askQuestion("Message Content: ");
            
            console.log(`✅ Using Email: ${email}`);
            console.log(`✅ Using Message: "${message}"`);

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
        console.log(`Relayer Status:   ${result.relayerStatus}`);
        
        console.log("\n🔐 [SECURITY TOKEN RECEIVED]");
        // --- DISPLAYING JWT ---
        console.log(result.jwt); 
        console.log("------------------------------------------");
        
        console.log("\n📡 [GATEWAY RESPONSE]");
        console.log(JSON.stringify(result.gatewayResult, null, 2));

    } catch (error) {
        console.error("\n❌ ERROR:", error.message || error);
    } finally {
        rl.close();
        process.exit(0);
    }
}

main();
