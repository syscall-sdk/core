/* SYSCALL-HEARTBEAT-SDK v2.0 (Dynamic Deposit) */

(function(global) {
    let ethers;

    if (typeof module !== 'undefined' && module.exports) {
        ethers = require("ethers");
    } else {
        if (!global.ethers) {
            console.error("❌ SYSCALL ERROR: 'ethers.js' missing.");
        } else {
            ethers = global.ethers;
        }
    }

    const FACTORY_ABI = [
        "function createJob(address _target, bytes calldata _data, uint256 _intervalSeconds) external payable",
        "function getJobs() external view returns (address[] memory)",
        "function minInitialDepositGas() external view returns (uint256)", // [AJOUT]
        "event JobCreated(address indexed jobAddress, address indexed owner, uint256 interval)"
    ];

    const JOB_ABI = [
        "function targetContract() view returns (address)", 
        "function data() view returns (bytes)",
        "function interval() view returns (uint256)",
        "function lastRun() view returns (uint256)",
        "function withdraw() external"
    ];

    class SyscallHeartbeat {
        constructor(signerSource = null) {
            if (!ethers) throw new Error("Library 'ethers.js' failed to load.");
            
            this.provider = null;
            this.signer = null;
            this.signerSource = signerSource;
            this.config = null;
        }

        // --- INTERNAL CONFIG ---
        async _fetchConfig() {
            if (this.config) return;
            try {
                let url = "/config"; 
                const response = await fetch(url);
                if (!response.ok) throw new Error("Relayer unavailable");
                this.config = await response.json();
            } catch (error) {
                console.error("[SDK] Config Error:", error);
                throw error;
            }
        }

        async _initProvider() {
            await this._fetchConfig();
            if (!this.provider) {
                this.provider = new ethers.JsonRpcProvider(this.config.rpc_url);
                this.provider.pollingInterval = 50;
            }
        }

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

        async _pollReceipt(txHash) {
            let attempts = 0;
            const maxAttempts = 400; 
            while (attempts < maxAttempts) {
                try {
                    const receipt = await this.provider.getTransactionReceipt(txHash);
                    if (receipt && receipt.blockNumber) return receipt;
                } catch (e) {}
                await new Promise(resolve => setTimeout(resolve, 50));
                attempts++;
            }
            throw new Error("Transaction validation timed out (Turbo Polling)");
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
                console.warn("[SDK] Fee fetch failed, falling back to MetaMask defaults.", e);
            }
            return options;
        }

        // --- CORE FEATURES ---
        
        // [NOUVEAU] Récupère le minInitialDepositGas depuis la Factory
        async getFactoryMinGas() {
            await this._initProvider();
            if (!this.config.factory_address) throw new Error("No Factory Address");
            const factory = new ethers.Contract(this.config.factory_address, FACTORY_ABI, this.provider);
            return await factory.minInitialDepositGas();
        }

        // [NOUVEAU] Helper pour avoir le gas price actuel
        async getGasPrice() {
            await this._initProvider();
            const feeData = await this.provider.getFeeData();
            return feeData.gasPrice || feeData.maxFeePerGas;
        }

        async deployJob(target, calldataHex, intervalSeconds, depositEth) {
            await this._initSigner();
            if (!this.config || !this.config.factory_address) throw new Error("SDK Configuration missing");

            const factory = new ethers.Contract(this.config.factory_address, FACTORY_ABI, this.signer);
            const depositWei = ethers.parseEther(depositEth.toString());

            const overrides = await this._getFastTxOptions(1200000);
            overrides.value = depositWei;

            console.log(`[SDK] Deploying Job... Target: ${target}`);
            const tx = await factory.createJob(target, calldataHex, intervalSeconds, overrides);
            
            console.log(`[SDK] TX Sent: ${tx.hash}`);
            const receipt = await this._pollReceipt(tx.hash);

            let newJobAddress = null;
            receipt.logs.forEach(log => {
                try {
                    const parsed = factory.interface.parseLog(log);
                    if (parsed.name === "JobCreated") newJobAddress = parsed.args[0];
                } catch (e) {}
            });

            return { txHash: tx.hash, jobAddress: newJobAddress, receipt: receipt };
        }

        async getJobsList() {
            await this._initProvider();
            if (!this.config.factory_address) throw new Error("No Factory Address in config");
            const factory = new ethers.Contract(this.config.factory_address, FACTORY_ABI, this.provider);
            return await factory.getJobs();
        }

        async getJobDetails(jobAddress) {
            await this._initProvider();
            const jobContract = new ethers.Contract(jobAddress, JOB_ABI, this.provider);
            try {
                const [targetContract, data, interval, balance] = await Promise.all([
                    jobContract.targetContract(), 
                    jobContract.data(),
                    jobContract.interval(),
                    this.provider.getBalance(jobAddress)
                ]);

                return {
                    address: jobAddress,
                    target: targetContract,
                    data: data,
                    interval: interval.toString(),
                    balance: ethers.formatEther(balance)
                };
            } catch (e) {
                return null;
            }
        }

        encodeCalldata(signature, argsString) {
            if (!signature || signature.trim() === "") return "0x";
            try {
                let args = [];
                const cleanArgs = argsString.trim();
                if (cleanArgs !== "") {
                    try {
                        args = JSON.parse(`[${cleanArgs}]`);
                    } catch (e) {
                        args = cleanArgs.split(',').map(s => s.trim());
                    }
                }
                const fullSig = signature.startsWith("function ") ? signature : `function ${signature}`;
                const iface = new ethers.Interface([fullSig]);
                const funcName = fullSig.split(' ')[1].split('(')[0];
                return iface.encodeFunctionData(funcName, args);
            } catch (e) {
                throw new Error(`Encoding Error: ${e.message}`);
            }
        }

        async cancelJob(jobAddress) {
            await this._initSigner();
            const jobContract = new ethers.Contract(jobAddress, JOB_ABI, this.signer);
            const overrides = await this._getFastTxOptions(200000);
            const tx = await jobContract.withdraw(overrides);
            return await this._pollReceipt(tx.hash);
        }

        async topUpJob(jobAddress, amountEth) {
            await this._initSigner();
            const overrides = await this._getFastTxOptions(100000);
            overrides.to = jobAddress;
            overrides.value = ethers.parseEther(amountEth.toString());
            const tx = await this.signer.sendTransaction(overrides);
            return await this._pollReceipt(tx.hash);
        }

        async getRelayerLogs() {
            try {
                await this._fetchConfig(); 
                const response = await fetch('/logs');
                if (!response.ok) return [];
                return await response.json();
            } catch (e) { return []; }
        }
    }

    if (typeof module !== 'undefined' && module.exports) { module.exports = SyscallHeartbeat; }
    else { global.SyscallHeartbeat = SyscallHeartbeat; }

})(typeof window !== 'undefined' ? window : this);
