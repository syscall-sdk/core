const { ethers } = require("ethers");

// --- Configuration ---
// RPC provided in requirements
const RPC_URL = "https://topstrike-megaeth-ws-proxy-100.fly.dev/rpc";
// Registry address provided in requirements
const REGISTRY_ADDRESS = "0x89a6A03E4FDec36269e525D435FC54caf2167996";

// --- ABIs (extracted from your uploaded files) ---

// 1. Registry ABI: To find the current logic contract
//
const REGISTRY_ABI = [
  "function syscallContract() view returns (address)"
];

// 2. Syscall Contract ABI: To check prices and pay
//
const SYSCALL_ABI = [
  "function services(string name) view returns (uint256)",
  "function pay(string name) payable"
];

class Syscall {
  /**
   * Initialize the SDK.
   * @param {string|object} signerSource - 
   * If string: Private Key (Backend mode).
   * If object: Ethereum Provider object (e.g., window.ethereum for Frontend).
   */
  constructor(signerSource) {
    this.provider = null;
    this.signer = null;
    this.signerSource = signerSource;
  }

  /**
   * Internal: Initialize the wallet/signer connection.
   */
  async _init() {
    if (this.signer) return; // Already initialized

    if (typeof this.signerSource === 'string') {
      // --- Backend Mode (Private Key) ---
      // Connect to the specific MegaETH RPC
      this.provider = new ethers.JsonRpcProvider(RPC_URL);
      this.signer = new ethers.Wallet(this.signerSource, this.provider);
      console.log("[SDK] Mode: Backend (Private Key)");
    } else {
      // --- Frontend Mode (Browser Injection / Metamask) ---
      // We wrap the injected provider (e.g. window.ethereum)
      this.provider = new ethers.BrowserProvider(this.signerSource);
      this.signer = await this.provider.getSigner();
      console.log("[SDK] Mode: Frontend (Browser Injection)");
    }
  }

  /**
   * Internal: Resolve the current SyscallContract address from the Registry.
   * Logic: Registry (0x89a...) -> calls syscallContract() -> returns Address
   */
  async _resolveContractAddress() {
    const registry = new ethers.Contract(REGISTRY_ADDRESS, REGISTRY_ABI, this.provider);
    const address = await registry.syscallContract();
    
    if (address === ethers.ZeroAddress) {
      throw new Error("SyscallContract address not set in Registry.");
    }
    return address;
  }

  /**
   * Main Function: Send an SMS.
   * @param {string} phoneNumber - The recipient's phone number.
   * @param {string} messageContent - The text to send.
   * @returns {Promise<string>} - The transaction hash.
   */
  async sendSMS(phoneNumber, messageContent) {
    await this._init(); // Ensure we are connected

    console.log(`[SDK] Initializing SMS to ${phoneNumber}...`);

    try {
      // 1. Get the authoritative SyscallContract address
      const contractAddress = await this._resolveContractAddress();
      console.log(`[SDK] Resolved SyscallContract at: ${contractAddress}`);

      // 2. Connect to the SyscallContract
      const syscallContract = new ethers.Contract(contractAddress, SYSCALL_ABI, this.signer);

      // 3. Get the base price for the 'sms' service
      // "function services(string name) view returns (uint256)"
      const serviceName = "sms";
      const basePriceWei = await syscallContract.services(serviceName);

      if (basePriceWei === 0n) {
        throw new Error(`Service '${serviceName}' is not active or price is zero.`);
      }

      // 4. Calculate the cost based on message size (in bytes)
      // Requirement: Multiply price by number of bytes in text
      const encoder = new TextEncoder();
      const messageBytes = encoder.encode(messageContent).length;
      
      // Calculation: Cost = Base Price * Byte Length
      const totalCost = basePriceWei * BigInt(messageBytes);

      console.log(`[SDK] Message size: ${messageBytes} bytes`);
      console.log(`[SDK] Base Price per byte: ${ethers.formatEther(basePriceWei)} ETH`);
      console.log(`[SDK] Total Cost: ${ethers.formatEther(totalCost)} ETH`);

      // 5. Execute the payment on-chain
      // "function pay(string name) payable"
      console.log("[SDK] Sending transaction to MegaETH...");
      
      const tx = await syscallContract.pay(serviceName, {
        value: totalCost
      });

      console.log(`[SDK] Transaction sent! Hash: ${tx.hash}`);
      
      // Wait for the transaction to be mined (Step 3)
      const receipt = await tx.wait();
      console.log(`[SDK] Confirmed in block: ${receipt.blockNumber}`);

      // Returns the hash so the developer can verify it or send it to the relayer
      return receipt.hash;

    } catch (error) {
      console.error("[SDK] Error sending SMS:", error);
      throw error;
    }
  }
}

module.exports = Syscall;
