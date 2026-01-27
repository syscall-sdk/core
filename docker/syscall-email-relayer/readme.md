# SYSCALL EMAIL [v2.1]

**Syscall Email** is a decentralized bridge enabling EVM smart contracts to trigger real-world emails. 

We abstract the complexity of SMTP servers and cryptographic proofs into a single line of JavaScript. You pay in ETH/Gas, we deliver the message. Security is enforced via a **Commit-Reveal** cryptographic handshake.

---

## ⚡ The SDK (Client-Side)

Stop running servers. Use the official SDK to inject Email capabilities directly into your Dapp or Bot.

### 📥 Download
**Latest Build (v2.9):**
`https://syscall-email-relayer.syscall-sdk.com/static/syscall-email-sdk.js`

---

## 💻 Integration Guide

### A. Browser (Dapps & Frontends)
Perfect for sending transaction receipts, alerts, or welcome emails directly from the user's wallet.

**1. Include the SDK**
```html
<script src="[https://cdnjs.cloudflare.com/ajax/libs/ethers/6.11.1/ethers.umd.min.js](https://cdnjs.cloudflare.com/ajax/libs/ethers/6.11.1/ethers.umd.min.js)"></script>
<script src="[https://syscall-email-relayer.syscall-sdk.com/static/syscall-email-sdk.js](https://syscall-email-relayer.syscall-sdk.com/static/syscall-email-sdk.js)"></script>
```

**2. Execute**
```javascript
// Initialize with window.ethereum (MetaMask, Rabin, etc.)
const syscall = new Syscall(window.ethereum); //

async function sendReceipt() {
    try {
        // Triggers wallet signature + Payment
        const receipt = await syscall.sendEmail(
            "alice@example.com",       // Destination
            "Payment Confirmed",       // Subject
            "DeFi Protocol",           // Sender Name
            "Your transaction 0x123... was successful." // Content Body
        );

        console.log("Proof of Dispatch:", receipt.txHash);
        console.log("Secret Revealed:", receipt.secret); //
    } catch (err) {
        console.error("Syscall Error:", err);
    }
}
```

### B. Backend (Node.js / Bots)
Ideal for monitoring scripts, server-side alerts, or CI/CD pipelines triggered by on-chain events.

**1. Setup**
Download `syscall-email-sdk.js` to your project root.
```bash
npm install ethers
wget [https://syscall-email-relayer.syscall-sdk.com/static/syscall-email-sdk.js](https://syscall-email-relayer.syscall-sdk.com/static/syscall-email-sdk.js)
```

**2. Execute**
```javascript
const Syscall = require('./syscall-email-sdk'); //

// Initialize with a Private Key (Backoffice Mode)
const syscall = new Syscall(process.env.ADMIN_PRIVATE_KEY); //

async function runMonitor() {
    console.log("⚡ Triggering Email Alert...");
    
    const tx = await syscall.sendEmail(
        "admin@platform.com",
        "System Critical",
        "Watchdog Bot",
        "Error: Liquidity Pool mismatch detected."
    );
    
    console.log(`✅ Sent. TX: ${tx.txHash}`);
}

runMonitor();
```

---

## ⚙️ How It Works (Under the Hood)

You don't need to understand this to use it, but here is the security model:

1.  **Commit (On-Chain):** The SDK calculates the cost (Gas + Protocol Fee), generates a random `secret`, and submits its hash to the blockchain.
2.  **Reveal (Off-Chain):** The SDK sends the email content + the raw `secret` to the Syscall Relayer via HTTPS.
3.  **Verify:** The Relayer hashes the `secret`. If it matches the on-chain commitment, the email is signed and dispatched via SMTP.
4.  **Delivery:** The Relayer consumes the payment on-chain to prevent replay attacks.

---

## 🛡️ Pricing & Limits

* **Model:** Pay-per-byte (ETH). Costs are calculated dynamically based on content size.
* **Payload Limit:** 1MB max per email.
* **Delivery:** Instant (dependent on block finality).

## 📜 License

MIT. Code is Law.

---
*Syscall Email - Communications at Kernel Speed.*
