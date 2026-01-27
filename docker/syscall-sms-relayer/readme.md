# SYSCALL SMS [v2.3]

**Syscall SMS** is a decentralized bridge enabling EVM smart contracts to trigger real-world SMS text messages. 

It leverages the **JMP.chat** infrastructure (XMPP-to-SMS) to route messages without centralized HTTP APIs like Twilio. Security is enforced via a **Commit-Reveal** cryptographic handshake, ensuring that the Relayer cannot spoof or censor messages without breaking mathematical proofs.

---

## ⚡ The Logic: Commit-Reveal

We do not simply "listen to events". We enforce a strict security handshake:

1.  **COMMIT (On-Chain):** The user/contract calculates the cost (Gas + Protocol Fee) and submits a hash of a randomly generated `secret`.
2.  **REVEAL (Off-Chain):** The SDK sends the payload + the raw `secret` to the Relayer via HTTPS.
3.  **VERIFY & DISPATCH:** The Relayer hashes the `secret`. If it matches the on-chain commitment, the SMS is routed via XMPP.
4.  **CONSUME:** The Relayer marks the payment as `consumed` on-chain to prevent replay attacks.

---

## 🚀 Quick Start (Integration)

### 1. Browser Integration (Dapps)
Allow your Dapp users to send SMS notifications directly from their wallet.

```javascript
import { Syscall } from './syscall-sms-sdk.js';

// Initialize with window.ethereum
const syscall = new Syscall(window.ethereum);

// Trigger Action (Requires Wallet Signature)
const tx = await syscall.sendSMS(
    "+15550199888",            // Target Phone (E.164)
    "Your loan is liquidated." // Content
);

console.log(`Proof: ${tx.txHash}`);
```

### 2. Backend Integration (Node.js)
Ideal for monitoring bots, server-side alerts, or CI/CD pipelines.

```javascript
require('dotenv').config();
const Syscall = require('./syscall-sms-sdk');

// Initialize with a Private Key (Backoffice Mode)
const syscall = new Syscall(process.env.ADMIN_PRIVATE_KEY);

await syscall.sendSMS(
    "+33612345678",
    "Server Alert: CPU Load > 90%"
);
```

---

## ⚙️ Architecture & Stack

### Smart Contract (`SyscallContract.sol`)
* **Pay-Per-Byte:** Costs are calculated dynamically based on payload size (`messageBytes * unitPrice`).
* **Registry:** Maintains a mapping of active services.
* **State Machine:** Tracks `paymentId` consumption status.

### The Relayer (`syscall-sms-relayer.py`)
* **XMPP / Jabber:** Uses `slixmpp` to connect to the JMP.chat network.
* **FastAPI:** High-performance Python gateway.
* **Validation:** Strict Regex checks on phone numbers to prevent injection.
* **Chain Writer:** Automatically calls `consumePayment()` on-chain after successful delivery.

---

## 🛠️ Self-Hosting (Run a Node)

Become a Relayer and provide infrastructure to the network.

### Prerequisites
* Python 3.9+
* A JMP.chat Account (JID + Password)
* EVM Wallet with dust ETH

### Configuration (`.env`)
```bash
SYSCALL-SMS-RELAYER-PORT=8080
SYSCALL-SMS-RELAYER-RPC_URL="[https://rpc.megaeth.systems](https://rpc.megaeth.systems)"
SYSCALL-SMS-RELAYER-OWNER_PRIVATE_KEY="0x..."
SYSCALL-SMS-RELAYER-SYSCALL_CONTRACT_ADDRESS="0x..."

# XMPP / JMP Configuration
SYSCALL-SMS-RELAYER-JMP_JID="your-id@cheogram.com"
SYSCALL-SMS-RELAYER-JMP_PASSWORD="your-xmpp-password"
SYSCALL-SMS-RELAYER-JMP_GATEWAY_SUFFIX="cheogram.com"
```

### Deploy
1.  **Deploy Contract:** Deploy `SyscallContract.sol`.
2.  **Configure Service:** Call `setService("sms", pricePerByte)` on the contract.
3.  **Run Relayer:**
    ```bash
    pip install -r requirements.txt
    python syscall-sms-relayer.py
    ```

---

## 🛡️ Security Model

| Threat | Mitigation |
| :--- | :--- |
| **Replay Attack** | Relayer calls `consumePayment(id)` on-chain. Contract rejects used IDs. |
| **Spam / DoS** | Pay-per-byte pricing + 2KB Payload Cap + 1024-bit Secret entropy. |
| **Injection** | Strict Regex `^\+?[1-9]\d{6,14}$` on destination. |
| **Front-running** | The `secret` is never broadcast on-chain, only its hash. |

## 📜 License

MIT. Code is Law.

---
*Syscall SMS - Communications at Kernel Speed.*
