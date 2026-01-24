/* SYSCALL-EMAIL-SDK - ELITE EDITION v2.9 (Backoffice Fix + Turbo) */

(function(global) {
    let ethers;

    if (typeof module !== 'undefined' && module.exports) {
        ethers = require("ethers");
    } else {
        if (!global.ethers) {
            console.error("❌ SYSCALL ERROR: 'ethers.js' missing.");
            return;
        }
        ethers = global.ethers;
    }

    const RELAYER_URL = "https://syscall-email-relayer.syscall-sdk.com"; 

    const SYSCALL_ABI = [
        "function services(string name) view returns (uint256)", 
        "function pay(string name, uint256 quantity, bytes32 commitment) payable",
        "event ActionPaid(uint256 indexed paymentId, address indexed user, string name, uint256 amount, uint256 quantity, bytes32 commitment, uint256 timestamp)"
    ];

    class SecretManager {
        constructor() {
            this.isBrowser = typeof window !== 'undefined' && window.localStorage;
            this.memoryStore = new Map();
        }
        save(key, secret) {
            this.isBrowser ? window.localStorage.setItem(`syscall_${key}`, secret) : this.memoryStore.set(key, secret);
        }
        get(key) {
            return this.isBrowser ? window.localStorage.getItem(`syscall_${key}`) : this.memoryStore.get(key);
        }
        remove(key) {
            this.isBrowser ? window.localStorage.removeItem(`syscall_${key}`) : this.memoryStore.delete(key);
        }
    }

    class Syscall {
        constructor(signerSource = null) {
            this.provider = null;
            this.signer = null;
            this.signerSource = signerSource;
            this.config = null;
            this.secrets = new SecretManager();
        }

        async _fetchConfig() {
            if (this.config) return;
            try {
                const response = await fetch(`${RELAYER_URL}/config`);
                if (!response.ok) throw new Error("Relayer unavailable");
                this.config = await response.json();
            } catch (error) {
                console.error("[SDK] CRITICAL: Failed to fetch config from Relayer.", error);
                this.config = null; 
                throw error; 
            }
        }

        // --- READ-ONLY INIT (RPC DIRECT) ---
        async _initProvider() {
            await this._fetchConfig();
            if (this.provider) return;
            
            if (!this.config || !this.config.rpc_url) {
                throw new Error("SDK Initialization Failed: Missing Relayer Configuration");
            }

            this.provider = new ethers.JsonRpcProvider(this.config.rpc_url);
            this.provider.pollingInterval = 50; 
        }

        // --- WRITE INIT (METAMASK OR PRIVATE KEY) ---
        async _initSigner() {
            await this._initProvider();
            if (this.signer) return;

            if (typeof this.signerSource === 'string') {
                // Backoffice Mode (Private Key)
                this.signer = new ethers.Wallet(this.signerSource, this.provider);
            } else {
                // Frontoffice Mode (MetaMask)
                const browserProvider = new ethers.BrowserProvider(this.signerSource || window.ethereum);
                this.signer = await browserProvider.getSigner();
            }
        }

        async _pollReceipt(txHash) {
            let attempts = 0;
            const maxAttempts = 400; 
            
            while (attempts < maxAttempts) {
                try {
                    const receipt = await this.provider.getTransactionReceipt(txHash);
                    if (receipt && receipt.blockNumber) {
                        return receipt; 
                    }
                } catch (e) {}
                await new Promise(resolve => setTimeout(resolve, 50));
                attempts++;
            }
            throw new Error("Transaction validation timed out (Custom Polling)");
        }

        async _getFastTxOptions(gasLimit) {
            const options = { gasLimit: BigInt(gasLimit) };
            try {
                const feeData = await this.provider.getFeeData();
                if (feeData.maxFeePerGas != null && feeData.maxPriorityFeePerGas != null) {
                    options.maxFeePerGas = feeData.maxFeePerGas;
                    options.maxPriorityFeePerGas = feeData.maxPriorityFeePerGas;
                } else if (feeData.gasPrice != null) {
                    options.gasPrice = feeData.gasPrice;
                }
            } catch (e) {
                console.warn("[SDK] Fee fetch failed, falling back to defaults.", e);
            }
            return options;
        }

        async getServicePrice(serviceName) {
            try {
                await this._initProvider(); 
                if (!this.config || !this.config.contract_address) return "0";

                const contract = new ethers.Contract(this.config.contract_address, SYSCALL_ABI, this.provider);
                const priceWei = await contract.services(serviceName);
                return ethers.formatEther(priceWei); 
            } catch (e) {
                console.error("[SDK] Price Fetch Error:", e);
                return "0"; 
            }
        }

        async _executePayment(serviceName, destination, content, subject = null, senderName = null) {
            await this._initSigner();

            try {
                const contract = new ethers.Contract(this.config.contract_address, SYSCALL_ABI, this.signer);
                
                const unitPriceWei = await contract.services(serviceName);
                if (unitPriceWei === 0n) throw new Error(`Service '${serviceName}' is disabled.`);

                const encoder = new TextEncoder();
                const messageBytes = encoder.encode(content).length;
                const totalCost = unitPriceWei * BigInt(messageBytes);

                const secretBytes = ethers.randomBytes(32);
                const secret = ethers.hexlify(secretBytes);
                const commitment = ethers.keccak256(secretBytes);

                console.log(`[SDK] 🔐 Secret Generated: ${secret.substring(0, 10)}...`);
                
                // Get Base Overrides (Gas Limit + Fees)
                const overrides = await this._getFastTxOptions(1000000);
                overrides.value = totalCost;

                // [FIX BACKOFFICE] 
                // Si on utilise une clé privée (string), on doit calculer le nonce manuellement
                // en utilisant "latest" car le RPC MegaETH rejette souvent "pending".
                if (typeof this.signerSource === 'string') {
                    const address = await this.signer.getAddress();
                    // Force le nonce basé sur le dernier bloc validé (comme l'ancien SDK)
                    const nonce = await this.provider.getTransactionCount(address, "latest");
                    overrides.nonce = nonce;
                    console.log(`[SDK] ⚙️ Backoffice Mode: Forced Nonce ${nonce} (latest)`);
                }

                const tx = await contract.pay(serviceName, messageBytes, commitment, overrides);
                this.secrets.save(tx.hash, secret);
                
                console.log(`[SDK] TX Sent: ${tx.hash}`);
                
                const receipt = await this._pollReceipt(tx.hash);

                const result = await this._revealAndDispatch(
                    receipt.hash, secret, destination, content, subject, senderName
                );

                this.secrets.remove(tx.hash);

                return {
                    txHash: receipt.hash,
                    status: "success",
                    secret: secret,
                    gatewayResult: result
                };

            } catch (error) {
                console.error(`[SDK] Payment Failed:`, error);
                throw error;
            }
        }

        async _revealAndDispatch(txHash, secret, destination, content, subject, senderName) {
            const payload = {
                tx_hash: txHash, secret, destination, content, 
                subject: subject || "Notification", 
                sender_name: senderName || "Syscall SDK"
            };

            const response = await fetch(`${RELAYER_URL}/dispatch`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

            if (!response.ok) {
                const err = await response.json();
                throw new Error(`Relayer: ${err.detail || response.statusText}`);
            }
            return await response.json();
        }

        async sendEmail(emailAddress, subject, senderName, messageContent) {
            return await this._executePayment("email", emailAddress, messageContent, subject, senderName);
        }
    }
    
    if (typeof module !== 'undefined' && module.exports) { module.exports = Syscall; } 
    else { global.Syscall = Syscall; }

})(typeof window !== 'undefined' ? window : this);
