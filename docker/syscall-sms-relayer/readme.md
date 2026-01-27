# SYSCALL SMS [v2.3.0]

**Syscall SMS** is a decentralized bridge enabling EVM smart contracts to trigger real-world SMS text messages. 

We abstract the complexity of XMPP and carrier routing into a single line of JavaScript. You pay in ETH/Gas, we deliver the message. Security is enforced via a **Commit-Reveal** cryptographic handshake.

---

## ⚡ The SDK (Client-Side)

Stop running servers. Use the official SDK to inject SMS capabilities directly into your Dapp or Bot.

### 📥 Download
**Latest Build (v2.9):**
`https://syscall-sms-relayer.syscall-sdk.com/static/syscall-sms-sdk.js`

---

## 💻 Integration Guide

### A. Browser (Dapps & Frontends)
Perfect for verifying user phone numbers or sending notifications upon transaction completion.

**1. Include the SDK**
```html
<script src="[https://cdnjs.cloudflare.com/ajax/libs/ethers/6.11.1/ethers.umd.min.js](https://cdnjs.cloudflare.com/ajax/libs/ethers/6.11.1/ethers.umd.min.js)"></script>
<script src="[https://syscall-sms-relayer.syscall-sdk.com/static/syscall-sms-sdk.js](https://syscall-sms-relayer.syscall-sdk.com/static/syscall-sms-sdk.js)"></script>
```

**2. Execute**
```javascript
// Initialize with window.ethereum (MetaMask, Rabin, etc.)
const syscall = new Syscall(window.ethereum); //

async function notifyUser() {
    try {
        // Triggers wallet signature + Payment
        const receipt = await syscall.sendSMS(
            "+15550199888",            // Target (E.164 Format)
            "Your DeFi position has been liquidated." // Content
        );

        console.log("Proof of Dispatch:", receipt.txHash);
        console.log("Secret Revealed:", receipt.secret); //
    } catch (err) {
        console.error("Syscall Error:", err);
    }
}
```

### B. Backend (Node.js / Bots)
Ideal for monitoring scripts, watchdogs, or CI/CD pipelines.

**1. Setup**
Download `syscall-sms-sdk.js` to your project root.
```bash
npm install ethers
wget [https://syscall-sms-relayer.syscall-sdk.com/static/syscall-sms-sdk.js](https://syscall-sms-relayer.syscall-sdk.com/static/syscall-sms-sdk.js)
```

**2. Execute**
```javascript
const Syscall = require('./syscall-sms-sdk'); //

// Initialize with a Private Key (Backoffice Mode)
const syscall = new Syscall(process.env.ADMIN_PRIVATE_KEY); //

async function runWatchdog() {
    console.log("⚡ Triggering SMS Alert...");
    
    const tx = await syscall.sendSMS(
        "+33612345678", 
        "CRITICAL: Server CPU Load > 95%"
    );
    
    console.log(`✅ Sent. TX: ${tx.txHash}`);
}

runWatchdog();
```

---

## ⚙️ How It Works (Under the Hood)

You don't need to understand this to use it, but here is the security model:

1.  **Commit (On-Chain):** The SDK generates a random `secret` and submits its hash to the blockchain along with the payment.
2.  **Reveal (Off-Chain):** The SDK sends the payload + the raw `secret` to the Syscall Relayer via HTTPS.
3.  **Verify:** The Relayer hashes the `secret`. If it matches the on-chain commitment, the SMS is routed via the XMPP network.
4.  **Delivery:** The message is delivered to the carrier network. The payment is consumed on-chain to prevent replay attacks.

---

## 🛡️ Pricing & Limits

* **Model:** Pay-per-byte (ETH). Pricing is dynamic based on network demand.
* **Payload Limit:** ~2KB per message (approx 10 SMS segments).
* **Anti-Spam:** Requires a valid E.164 phone number format (e.g., `+1...`).

## 📜 License

MIT. Code is Law.

---
*Syscall SMS - Communications at Kernel Speed.*
