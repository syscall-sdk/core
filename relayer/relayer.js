const { ethers } = require("ethers");

// ==========================================
// 1. CONFIGURATION
// ==========================================

// 🟢 REPLACE THIS WITH YOUR DEPLOYED REGISTRY ADDRESS
const REGISTRY_ADDRESS = "0x89a6A03E4FDec36269e525D435FC54caf2167996"; 

// 🟢 REPLACE WITH YOUR RPC URL (e.g., Alchemy, Infura, or Localhost)
// NOTE: If you are using Remix VM, this script CANNOT connect to it.
// You must deploy to Sepolia or use a local Ganache/Hardhat node.
const RPC_URL = "https://topstrike-megaeth-ws-proxy-100.fly.dev/rpc"; 
// OR for local node: "http://127.0.0.1:8545"

// ==========================================
// 2. MINIMAL ABIS (No JSON files needed)
// ==========================================

// ABI to query the Registry
const REGISTRY_ABI = [
    "function syscallContract() view returns (address)",
    "event SyscallContractUpdated(address indexed oldAddress, address indexed newAddress)"
];

// ABI to listen to the Logic Contract
const SYSCALL_ABI = [
    "event ActionPaid(address indexed user, string name, uint256 amount, uint256 timestamp)"
];

// ==========================================
// 3. RELAYER LOGIC
// ==========================================

async function startRelayer() {
    console.log("🚀 Starting Syscall Relayer...");
    
    // Initialize provider
    const provider = new ethers.JsonRpcProvider(RPC_URL);

    // 1. Connect to the Registry
    const registry = new ethers.Contract(REGISTRY_ADDRESS, REGISTRY_ABI, provider);

    // 2. Fetch the current active Logic Contract address
    console.log("🔍 Querying Registry for active contract...");
    const currentLogicAddress = await registry.syscallContract();
    
    if (currentLogicAddress === ethers.ZeroAddress) {
        console.error("❌ Error: Registry points to 0x000. Did you call setSyscallContract()?");
        return;
    }

    console.log(`✅ Active SyscallContract found at: ${currentLogicAddress}`);

    // 3. Connect to the Logic Contract
    const syscallContract = new ethers.Contract(currentLogicAddress, SYSCALL_ABI, provider);

    // 4. Listen for events
    console.log("👂 Listening for 'ActionPaid' events...");

    syscallContract.on("ActionPaid", (user, name, amount, timestamp, event) => {
        console.log("\n----------------------------------------");
        console.log("💰 PAYMENT DETECTED!");
        console.log(`👤 User      : ${user}`);
        console.log(`🛒 Service   : "${name}"`);
        console.log(`💸 Amount    : ${ethers.formatEther(amount)} ETH`);
        console.log(`⏰ Timestamp : ${timestamp}`);
        console.log("----------------------------------------");

        // Trigger off-chain logic
        handleServiceDispatch(name, user);
    });
}

/**
 * Handles the logic based on the service name requested.
 */
function handleServiceDispatch(serviceName, userAddress) {
    if (serviceName === "email") {
        console.log(`📧 ACTION: Sending email to user associated with ${userAddress}...`);
        // Add your email sending logic here
    } else if (serviceName === "sms") {
        console.log(`📱 ACTION: Sending SMS to user associated with ${userAddress}...`);
    } else {
        console.log(`⚠️ WARNING: Unknown service requested: ${serviceName}`);
    }
}

// Start the script
startRelayer().catch((error) => {
    console.error("❌ Fatal Error:", error);
});
