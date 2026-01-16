const readline = require('readline');
const Syscall = require('./syscall-email-sdk'); 
require('dotenv').config(); 

const rl = readline.createInterface({
    input: process.stdin, output: process.stdout
});

const askQuestion = (query) => new Promise((resolve) => rl.question(query, resolve));

async function main() {
    console.clear();
    console.log("==========================================");
    console.log("      SYSCALL SDK - CLI TESTER            ");
    console.log("      (Email Only Edition)                ");
    console.log("==========================================\n");

    try {
        let privateKey = process.env.PRIVATE_KEY;
        if (!privateKey) {
            privateKey = await askQuestion("Enter Wallet Private Key: ");
        } else {
            console.log("✅ Using Private Key from .env");
        }

        console.log("[1/3] Initializing SDK...");
        const syscall = new Syscall(privateKey);

        console.log("\n[2/3] Preparing Email Transaction:");
        
        let email = process.env.TEST_EMAIL || await askQuestion("Target Email Address: ");
        let subject = process.env.TEST_SUBJECT || await askQuestion("Email Subject: ");
        let senderName = process.env.TEST_SENDER_NAME || await askQuestion("Sender Name (Display Name): "); 
        let message = process.env.TEST_MESSAGE || await askQuestion("Message Content: ");
        
        console.log(`✅ Using Email: ${email}`);
        console.log(`✅ Using Subject: "${subject}"`);
        console.log(`✅ Using Sender: "${senderName}"`);
        console.log(`✅ Using Message: "${message}"`);

        console.log("\n[3/3] Processing Payment & Action...");
        console.log("------------------------------------------");
        
        // Passing the custom sender name to the SDK
        let result = await syscall.sendEmail(email, subject, senderName, message);

        // --- Success Output ---
        console.log("------------------------------------------");
        console.log("\n[SUCCESS] 🚀");
        console.log(`Transaction Hash: ${result.txHash}`);
        console.log(`Relayer Status:   ${result.relayerStatus}`);
        
        console.log("\n🔐 [COMMIT-REVEAL SECRET]");
        console.log(result.secret); 
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
