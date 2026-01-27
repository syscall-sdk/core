# SYSCALL EMAIL [v2.1]

**Syscall Email** is a decentralized bridge enabling EVM smart contracts to trigger real-world emails. 

Unlike centralized Web2 APIs (SendGrid, Mailgun), Syscall Email uses a **Commit-Reveal** cryptographic scheme. The content and dispatch instructions are cryptographically linked to the on-chain payment, ensuring that the Relayer cannot spoof or censor messages without breaking mathematical proofs.

---

## ⚡ The Logic: Commit-Reveal

We do not simply "listen to events". We enforce a strict security handshake:

1.  **COMMIT (On-Chain):** The user/contract calculates the cost (Gas + Protocol Fee) and submits a hash of a randomly generated `secret`.
2.  **REVEAL (Off-Chain):** The SDK sends the payload + the raw `secret` to the Relayer via HTTPS.
3.  **VERIFY & DISPATCH:** The Relayer hashes the `secret`. If it matches the on-chain commitment, the email is sent via SMTP.
4.  **CONSUME:** The Relayer marks the payment as `consumed` on-chain to prevent replay attacks.

---

## 🚀 Quick Start (Integration)

### 1. Browser Integration (Dapps)
Allow your Dapp users to send emails directly from their wallet (MetaMask, etc.).

```javascript
import { Syscall } from './syscall-email-sdk.js';

// Initialize with window.ethereum
const syscall = new Syscall(window.ethereum);

// Trigger Action (Requires Wallet Signature)
const tx = await syscall.sendEmail(
    "alice@example.com",       // Destination
    "Yield Alert",             // Subject
    "DeFi Protocol",           // Sender Name
    "Your position is low."    // Content body
);

console.log(`Proof: ${tx.txHash}`);
```

### 2. Backend Integration (Node.js)
Ideal for monitoring bots, server-side notifications, or CI/CD pipelines triggered by chain state.

```javascript
require('dotenv').config();
const Syscall = require('./syscall-email-sdk');

// Initialize with a Private Key (Backoffice Mode)
const syscall = new Syscall(process.env.ADMIN_PRIVATE_KEY);

await syscall.sendEmail(
    "admin@platform.com",
    "Server Status",
    "Watchdog",
    "System Critical Error: 0x54F..."
);
```

---

## ⚙️ Architecture & Stack

### Smart Contract (`SyscallContract.sol`)
* **Pay-Per-Byte:** Costs are calculated dynamically based on payload size to prevent spam.
* **Registry:** Maintains a mapping of active services and their unit prices.
* **State Machine:** Tracks `paymentId` consumption status.

### The Relayer (`syscall-email-relayer.py`)
* **FastAPI / Async:** High-performance Python gateway.
* **DoS Protection:** 1MB hard limit per payload.
* **Background Tasks:** Non-blocking SMTP dispatch.
* **Chain Writer:** Automatically calls `consumePayment()` on-chain after successful delivery.

---

## 🛠️ Self-Hosting (Run a Node)

Become a Relayer and provide infrastructure to the network.

### Prerequisites
* Python 3.9+
* An SMTP Server (Postfix, SendGrid, SES)
* EVM Wallet with dust ETH

### Configuration (`.env`)
```bash
SYSCALL-EMAIL-RELAYER-PORT=8080
SYSCALL-EMAIL-RELAYER-RPC_URL="[https://rpc.megaeth.systems](https://rpc.megaeth.systems)"
SYSCALL-EMAIL-RELAYER-OWNER_PRIVATE_KEY="0x..."
SYSCALL-EMAIL-RELAYER-SYSCALL_CONTRACT_ADDRESS="0x..."

# SMTP Settings
SYSCALL-EMAIL-RELAYER-SMTP_HOST="smtp.provider.com"
SYSCALL-EMAIL-RELAYER-SMTP_PORT=587
SYSCALL-EMAIL-RELAYER-SMTP_USER="apikey"
SYSCALL-EMAIL-RELAYER-SMTP_PASSWORD="secret-password"
SYSCALL-EMAIL-RELAYER-SMTP_FROM_EMAIL="noreply@syscall-sdk.com"
```

### Deploy
1.  **Deploy Contract:** Deploy `SyscallContract.sol` using Remix or Hardhat.
2.  **Configure Service:** Call `setService("email", pricePerByte)` on the contract.
3.  **Run Relayer:**
    ```bash
    pip install -r requirements.txt
    python syscall-email-relayer.py
    ```

---

## 🛡️ Security Model

| Threat | Mitigation |
| :--- | :--- |
| **Replay Attack** | Relayer calls `consumePayment(id)` on-chain. Contract rejects used IDs. |
| **Spam / DoS** | Pay-per-byte pricing + 1MB Payload Cap + 1024-bit Secret entropy. |
| **Censorship** | Commit-Reveal scheme proves the content was paid for. |
| **Front-running** | The `secret` is never broadcast on-chain, only its hash. |

## 📜 License

MIT. Code is Law.

---
*Syscall Email - Communications at Kernel Speed.*
