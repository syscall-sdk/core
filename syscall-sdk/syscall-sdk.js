const { ethers } = require("ethers");

// --- Configuration ---
const RPC_URL = "https://topstrike-megaeth-ws-proxy-100.fly.dev/rpc";
const REGISTRY_ADDRESS = "0x68704764C29886ed623b0f3CD30516Bf0643f390";
const RELAYER_URL = process.env.RELAYER_URL || "http://localhost:8080"; 

// --- ABIs ---
const REGISTRY_ABI = ["function syscallContract() view returns (address)"];
const SYSCALL_ABI = ["function services(string name) view returns (uint256)", "function pay(string name) payable"];

class Syscall {
  constructor(signerSource) {
    this.provider = null;
    this.signer = null;
    this.signerSource = signerSource;
  }

  async _init() {
    if (this.signer) return; 

    if (typeof this.signerSource === 'string') {
      this.provider = new ethers.JsonRpcProvider(RPC_URL);
      this.signer = new ethers.Wallet(this.signerSource, this.provider);
      console.log("[SDK] Mode: Backend (Private Key)");
    } else {
      this.provider = new ethers.BrowserProvider(this.signerSource);
      this.signer = await this.provider.getSigner();
      console.log("[SDK] Mode: Frontend (Browser Injection)");
    }
  }

  async _resolveContractAddress() {
    const registry = new ethers.Contract(REGISTRY_ADDRESS, REGISTRY_ABI, this.provider);
    const address = await registry.syscallContract();
    if (address === ethers.ZeroAddress) throw new Error("SyscallContract address not set.");
    return address;
  }

  async _notifyRelayer(txHash) {
    console.log("[SDK] [Step 4] Connecting to Relayer...");

    const signature = await this.signer.signMessage(txHash);
    const senderAddress = await this.signer.getAddress();

    const payload = {
        tx_hash: txHash,
        signature: signature,
        sender: senderAddress
    };

    try {
        const response = await fetch(`${RELAYER_URL}/verify`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        if (!response.ok) throw new Error(`Relayer Error: ${response.statusText}`);
        const data = await response.json();
        console.log("[SDK] [Step 6] Relayer Response: Authorized ✅");
        return data;

    } catch (error) {
        console.error("[SDK] Failed to contact Relayer:", error.message);
        throw error; // Propagate error so test script knows it failed
    }
  }

  async _executePayment(serviceName, content) {
    await this._init();

    try {
      // 1. Resolve Contract
      const contractAddress = await this._resolveContractAddress();
      console.log(`[SDK] Resolved SyscallContract at: ${contractAddress}`);

      // 2. Connect to Contract
      const syscallContract = new ethers.Contract(contractAddress, SYSCALL_ABI, this.signer);

      // 3. Get Base Price
      const basePriceWei = await syscallContract.services(serviceName);
      if (basePriceWei === 0n) throw new Error(`Service '${serviceName}' is not active.`);

      // 4. Calculate Cost
      const encoder = new TextEncoder();
      const messageBytes = encoder.encode(content).length;
      const totalCost = basePriceWei * BigInt(messageBytes);

      // --- LOGS DETAILED (Restored from Screenshot) ---
      console.log(`[SDK] Service: ${serviceName.toUpperCase()}`);
      console.log(`[SDK] Message size: ${messageBytes} bytes`);
      console.log(`[SDK] Base Price per byte: ${ethers.formatEther(basePriceWei)} ETH`);
      console.log(`[SDK] Total Cost: ${ethers.formatEther(totalCost)} ETH`);
      // ------------------------------------------------

      // 5. Pay
      console.log("[SDK] Sending transaction to MegaETH...");
      const tx = await syscallContract.pay(serviceName, { value: totalCost });
      console.log(`[SDK] Transaction sent! Hash: ${tx.hash}`);
      
      const receipt = await tx.wait();
      console.log(`[SDK] Confirmed in block: ${receipt.blockNumber}`);

      // 6. Notify Relayer
      const relayerResult = await this._notifyRelayer(receipt.hash);

      return {
          txHash: receipt.hash,
          relayerStatus: relayerResult.status,
          jwt: relayerResult.jwt
      };

    } catch (error) {
      console.error(`[SDK] Error executing ${serviceName}:`, error);
      throw error;
    }
  }

  async sendSMS(phoneNumber, messageContent) {
    console.log(`[SDK] Initializing SMS to ${phoneNumber}...`);
    return await this._executePayment("sms", messageContent);
  }

  async sendEmail(emailAddress, messageContent) {
    console.log(`[SDK] Initializing Email to ${emailAddress}...`);
    return await this._executePayment("email", messageContent);
  }
}

module.exports = Syscall;
