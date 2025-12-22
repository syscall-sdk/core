const { ethers } = require("ethers");

// --- Configuration ---
const RPC_URL = process.env.RPC_URL || "https://topstrike-megaeth-ws-proxy-100.fly.dev/rpc";
const REGISTRY_ADDRESS = process.env.REGISTRY_ADDRESS || "0x68704764C29886ed623b0f3CD30516Bf0643f390";
const RELAYER_URL = process.env.RELAYER_URL || "http://localhost:8080"; 

const REGISTRY_ABI = ["function syscallContract() view returns (address)"];

// MODIFIED ABI: pay accepts (string name, uint256 quantity)
const SYSCALL_ABI = [
    "function services(string name) view returns (uint256)", 
    "function pay(string name, uint256 quantity) payable" 
];

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
    console.log("[SDK] [Step 4] Requesting Authorization from Relayer...");
    const signature = await this.signer.signMessage(txHash);
    const senderAddress = await this.signer.getAddress();

    const response = await fetch(`${RELAYER_URL}/verify`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tx_hash: txHash, signature: signature, sender: senderAddress })
    });

    if (!response.ok) throw new Error(`Relayer Verification Failed: ${response.statusText}`);
    const data = await response.json();
    console.log("[SDK] [Step 6] JWT Received ✅");
    return data.jwt;
  }

  async _deliverAction(jwt, destination, content) {
    console.log("[SDK] [Step 7] Dispatching payload to Gateway...");
    
    const response = await fetch(`${RELAYER_URL}/dispatch`, {
        method: 'POST',
        headers: { 
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${jwt}`
        },
        body: JSON.stringify({ destination: destination, content: content })
    });

    if (!response.ok) {
        const err = await response.json();
        throw new Error(`Gateway Delivery Failed: ${err.detail || response.statusText}`);
    }
    
    const ack = await response.json();
    console.log("[SDK] [Step 9] Acknowledgment Received 📡");
    return ack;
  }

  async _executePayment(serviceName, destination, content) {
    await this._init();

    try {
      const contractAddress = await this._resolveContractAddress();
      console.log(`[SDK] Resolved SyscallContract at: ${contractAddress}`);
      const syscallContract = new ethers.Contract(contractAddress, SYSCALL_ABI, this.signer);
      
      const unitPriceWei = await syscallContract.services(serviceName);
      if (unitPriceWei === 0n) throw new Error(`Service '${serviceName}' inactive.`);

      // Calculate Length
      const encoder = new TextEncoder();
      const messageBytes = encoder.encode(content).length;
      
      // Calculate Total Cost
      const totalCost = unitPriceWei * BigInt(messageBytes);

      console.log(`[SDK] Service: ${serviceName.toUpperCase()} | Length: ${messageBytes} chars | Cost: ${ethers.formatEther(totalCost)} ETH`);
      console.log("[SDK] Sending transaction to MegaETH...");
      
      // Pass length to the contract
      const tx = await syscallContract.pay(serviceName, messageBytes, { value: totalCost });
      
      console.log(`[SDK] TX Sent: ${tx.hash}`);
      const receipt = await tx.wait();
      console.log(`[SDK] Confirmed in block: ${receipt.blockNumber}`);

      const jwt = await this._notifyRelayer(receipt.hash);
      const ackData = await this._deliverAction(jwt, destination, content);

      return {
          txHash: receipt.hash,
          relayerStatus: ackData.status,
          jwt: jwt,
          gatewayResult: ackData,
          consumptionTx: ackData.meta.consumptionTx 
      };

    } catch (error) {
      console.error(`[SDK] Error executing ${serviceName}:`, error);
      throw error;
    }
  }

  async sendSMS(phoneNumber, messageContent) {
    return await this._executePayment("sms", phoneNumber, messageContent);
  }

  async sendEmail(emailAddress, messageContent) {
    return await this._executePayment("email", emailAddress, messageContent);
  }
}

module.exports = Syscall;
