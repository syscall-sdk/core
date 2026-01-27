# SYSCALL HEARTBEAT

**Syscall Heartbeat** is a decentralized, permissionless infrastructure that transforms passive EVM smart contracts into active, self-executing agents. 

It creates an incentivized market where independent actors ("Relayers") compete to execute scheduled tasks for users in exchange for an algorithmic reward. No centralized servers. No monthly subscriptions. Just code and gas.

---

## ⚡ The Problem: The Passive Ledger

Smart contracts are lazy. They cannot self-execute or wake up at scheduled intervals. To trigger a function every 24 hours (e.g., harvesting yield, updating oracles, paying salaries), you usually have to:
1.  **Trust a centralized server** (AWS cron job + private key = security risk).
2.  **Manual execution** (Human error).
3.  **Use complex DAO networks** (Overkill for simple automation).

## 💎 The Solution: Protocol Architecture

Syscall Heartbeat utilizes a **Hub-and-Spoke** architecture combining **EIP-1167 Minimal Proxies** with **Dynamic On-Chain Gas Metering**.

### 1. The Factory (Registry)
The central hub that manages job deployment and global gas governance. It enforces solvency thresholds and protocol fees.

### 2. The Job (Robot)
A sovereign contract owned by you. It holds your ETH credits and contains your execution logic:
* **Target:** The contract to call.
* **Calldata:** The specific function and arguments.
* **Interval:** How often to execute (e.g., every 3600 seconds).

### 3. The Relayer (Runner)
Off-chain bots (Python/Rust/Go) that monitor the network. When `block.timestamp >= lastRun + interval`, they execute the job and get **instantly reimbursed**.

---

## ⚙️ How It Works (v2.0 Mechanics)

### Dynamic Gas Metering & Reimbursement
Unlike v1 (fixed markup), v2.0 calculates the exact cost of execution inside the transaction to protect Relayers from volatility.

```solidity
// Simplified Logic
uint256 startGas = gasleft();

// ... Execute User Task ...

uint256 gasUsed = startGas - gasleft();
uint256 totalBill = (gasUsed + overhead + relayerFee) * tx.gasprice;

// Instant atomic repayment
(bool paid, ) = msg.sender.call{value: totalBill}("");
```

### The "Zombie Killer" Pruning Mechanism
To prevent state bloat, the protocol enforces strict hygiene.
1.  **Pre-Flight Check:** Before execution, the Job checks if it has enough ETH for the *next* run.
2.  **Liquidation:** If a Job becomes insolvent (balance < `solvencyThreshold`), the Relayer triggers a **Liquidation**.
3.  **Bounty:** The Job is removed from the registry, and its remaining dust balance is swept to the Relayer as a reward.

---

## 🚀 Quick Start (For Users)

### Deploy a Heartbeat Job
You can deploy a job programmatically via the Factory.

```solidity
interface IHeartbeatFactory {
    function createJob(
        address _target, 
        bytes calldata _data, 
        uint256 _intervalSeconds
    ) external payable;
}

// Example: Call harvest() on a Vault every 6 hours
// Send enough ETH to cover gas for future runs!
factory.createJob{value: 0.5 ether}(
    vaultAddress,
    abi.encodeWithSignature("harvest()"),
    21600 // 6 hours
);
```

### Manage Your Job
The returned address is your **Job Contract**. You can top it up or cancel it at any time.
* **Top Up:** Simply send ETH to the Job address.
* **Withdraw:** Call `withdraw()` from the owner wallet to cancel the job and retrieve funds.

---

## 🤖 Run a Relayer (For Keepers)

Monetize your uptime by running a Relayer node. You earn `relayerFeeGas * tx.gasprice` on every execution + Liquidation Bounties.

### Requirements
* Python 3.9+
* FastAPI / Web3.py
* An EVM Wallet with dust ETH (for gas)

### Setup
1.  Clone the repo.
2.  Set environment variables:
    ```bash
    export SYSCALL_HEARTBEAT_RPC_URL="[https://rpc.megaeth.systems](https://rpc.megaeth.systems)"
    export SYSCALL_HEARTBEAT_RELAYER_KEY="0xYourPrivateKey..."
    export SYSCALL_HEARTBEAT_FACTORY_ADDRESS="0x..."
    ```
3.  Run the Relayer:
    ```bash
    python syscall-heartbeat-relayer.py
    ```
4.  **Dashboard:** Access your local dashboard at `http://localhost:8080` to view live feed and logs.

---

## 🛡️ Security & Audits

* **Reentrancy:** Protected via Checks-Effects-Interactions pattern. `lastRun` is updated before the external call.
* **Flash Loans:** N/A. The protocol does not lend funds.
* **Dos Protection:** `O(1)` deletion algorithm (Swap-and-Pop) ensures cleanups are always cheap, regardless of registry size.

## 📜 License

MIT. Build, fork, and automate.

---
*Syscall Heartbeat - The Pulse of the Chain.*
