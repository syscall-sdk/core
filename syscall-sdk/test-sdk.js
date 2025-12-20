const readline = require('readline');
const Syscall = require('./syscall-sdk'); // Imports your SDK
require('dotenv').config(); // Loads variables from .env if present

// Create an interface for reading input from the console
const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout
});

// Helper function to ask questions using Promises
const askQuestion = (query) => {
    return new Promise((resolve) => rl.question(query, resolve));
};

async function main() {
    console.clear();
    console.log("==========================================");
    console.log("      SYSCALL SDK - CLI TESTER            ");
    console.log("==========================================\n");

    try {
        // 1. Get Private Key
        // Priority: Check .env file first, otherwise ask user
        let privateKey = process.env.PRIVATE_KEY;
        
        if (!privateKey) {
            console.log("No PRIVATE_KEY found in .env file.");
            privateKey = await askQuestion("Enter your Wallet Private Key: ");
        } else {
            console.log("Using Private Key from .env file.");
        }

        if (!privateKey.startsWith("0x")) {
            console.warn("Warning: Private key usually starts with '0x'.");
        }

        // 2. Initialize SDK
        console.log("\n[1/4] Initializing SDK...");
        const syscall = new Syscall(privateKey);

        // 3. Get Recipient Information
        console.log("\n[2/4] Enter Transaction Details:");
        const phoneNumber = await askQuestion("Target Phone Number (e.g. +33612345678): ");
        const message = await askQuestion("Message Content: ");

        if (!phoneNumber || !message) {
            throw new Error("Phone number and message are required.");
        }

        // 4. Execute Transaction
        console.log("\n[3/4] Processing Payment & Action...");
        console.log("------------------------------------------");
        
        // Call the SDK function created previously
        const txHash = await syscall.sendSMS(phoneNumber, message);

        // 5. Success Output
        console.log("------------------------------------------");
        console.log("\n[4/4] SUCCESS! 🚀");
        console.log(`Transaction Hash: ${txHash}`);
        console.log(`Explorer Link: https://megaeth-testnet.explorer.io/tx/${txHash}`); // Example link
        
    } catch (error) {
        console.error("\n❌ ERROR:");
        console.error(error.message || error);
    } finally {
        rl.close();
        process.exit(0);
    }
}

main();
