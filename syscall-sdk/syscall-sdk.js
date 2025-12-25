/* SYSCALL SDK - UNIVERSAL EDITION */

(function(global) {
    let ethers;

    if (typeof module !== 'undefined' && module.exports) {
        ethers = require("ethers");
    } else {
        if (!global.ethers) {
            console.error("❌ SYSCALL ERROR: 'ethers.js' library must be loaded BEFORE this SDK.");
            return;
        }
        ethers = global.ethers;
    }

    const RELAYER_URL = "https://syscall-relayer.syscall-sdk.com";

    const SYSCALL_ABI = [
        "function services(string name) view returns (uint256)", 
        "function pay(string name, uint256 quantity) payable" 
    ];

    class Syscall {
        constructor(signerSource) {
            this.provider = null;
            this.signer = null;
            this.signerSource = signerSource;
            this.config = null; 
        }

        async _fetchConfig() {
            if (this.config) return;

            try {
                console.log(`[SDK] 📡 Contacting Relayer for config at ${RELAYER_URL}...`);
                const response = await fetch(`${RELAYER_URL}/config`);
                
                if (!response.ok) throw new Error(`Failed to fetch config: ${response.statusText}`);
                
                this.config = await response.json();
                
                if (!this.config.rpc_url || !this.config.contract_address) {
                    throw new Error("Invalid config received from Relayer");
                }

                console.log(`[SDK] ✅ Config received. Target: ${this.config.contract_address}`);
            } catch (error) {
                console.error("[SDK] ❌ Initialization Error:", error);
                throw error;
            }
        }

        async _init() {
            await this._fetchConfig();

            if (this.signer) return;

            if (typeof this.signerSource === 'string') {
                this.provider = new ethers.JsonRpcProvider(this.config.rpc_url);
                this.signer = new ethers.Wallet(this.signerSource, this.provider);
                console.log("[SDK] Mode: Backend (Private Key)");
            } else {
                this.provider = new ethers.BrowserProvider(this.signerSource);
                this.signer = await this.provider.getSigner();
                console.log("[SDK] Mode: Frontend (Browser Injection)");
            }
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
                const contractAddress = this.config.contract_address;
                const syscallContract = new ethers.Contract(contractAddress, SYSCALL_ABI, this.signer);
                
                const unitPriceWei = await syscallContract.services(serviceName);
                if (unitPriceWei == 0) throw new Error(`Service '${serviceName}' inactive.`); 

                const encoder = new TextEncoder();
                const messageBytes = encoder.encode(content).length;
                const totalCost = unitPriceWei * BigInt(messageBytes);

                console.log(`[SDK] Service: ${serviceName.toUpperCase()} | Length: ${messageBytes} chars | Cost: ${ethers.formatEther(totalCost)} ETH`);
                console.log("[SDK] Sending transaction...");
                
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
    
    if (typeof module !== 'undefined' && module.exports) {
        module.exports = Syscall;
    } else {
        global.Syscall = Syscall;
    }

})(typeof window !== 'undefined' ? window : this);
