/* SYSCALL-EMAIL-SDK - ELITE EDITION v2.3 (FIXED) */

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
                console.error("[SDK] Config Error:", error);
                this.config = { rpc_url: "https://rpc.ankr.com/eth_sepolia" }; 
            }
        }

        // --- READ-ONLY INIT (Fast, No Wallet Popup) ---
        async _initProvider() {
            await this._fetchConfig();
            if (this.provider) return;

            if (this.config && this.config.rpc_url) {
                this.provider = new ethers.JsonRpcProvider(this.config.rpc_url);
            } else if (this.signerSource && this.signerSource.request) {
                this.provider = new ethers.BrowserProvider(this.signerSource);
            } else {
                this.provider = new ethers.JsonRpcProvider("https://rpc.ankr.com/eth_sepolia");
            }
        }

        // --- WRITE INIT (Wallet Popup) ---
        async _initSigner() {
            await this._initProvider();
            if (this.signer) return;

            if (typeof this.signerSource === 'string') {
                this.signer = new ethers.Wallet(this.signerSource, this.provider);
            } else {
                const browserProvider = new ethers.BrowserProvider(this.signerSource || window.ethereum);
                this.signer = await browserProvider.getSigner();
            }
        }

        /**
         * GET SERVICE PRICE
         * Returns STRING (ex: "0.001") compatible with UI.
         */
        async getServicePrice(serviceName) {
            try {
                await this._initProvider(); 
                
                if (!this.config || !this.config.contract_address) {
                    return "0";
                }

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
                
                const tx = await contract.pay(serviceName, messageBytes, commitment, { value: totalCost });
                this.secrets.save(tx.hash, secret);
                
                console.log(`[SDK] TX Sent: ${tx.hash}`);
                const receipt = await tx.wait();

                const result = await this._revealAndDispatch(
                    receipt.hash, secret, destination, content, subject, senderName
                );

                this.secrets.remove(tx.hash);

                return {
                    txHash: receipt.hash,
                    status: "success",
                    secret: secret, // ✅ CRITICAL FIX: Returning secret for UI display
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
