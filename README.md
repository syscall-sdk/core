```text
   _____ __  __  _____   _____          _      _             _____  _____  _  __
  / ____|\ \/ / / ____| / ____|   /\   | |    | |           / ____||  __ \| |/ /
 | (___   \  / | (___  | |       /  \  | |    | |   ______ | (___  | |  | | ' / 
  \___ \   \ \  \___ \ | |      / /\ \ | |    | |  |______| \___ \ | |  | |  <  
  ____) |   | | ____) || |____ / ____ \| |____| |____       ____) || |__| | . \ 
 |_____/    |_||_____/  \_____/_/    \_\______|______|     |_____/ |_____/|_|\_\
                                                                                
  > the reverse oracle
  > version: 0.1.0 / alpha
```

--------------------------------

## 0x00: the manifesto

syscall-sdk is the missing link between blockchain and reality<br>
while traditional oracles import real-world data to the blockchain, syscall-sdk exports blockchain actions to the real world<br>
syscall-sdk extends the blockchain's capabilities beyond its native environment<br>
with just a single line of code, developers can send emails and sms, post on x (twitter), control telegram bots, or trigger ai agents<br>

--------------------------------

## 0x01: the paradigm shift

traditional oracles are **read-only**: they pull data from the world onto the chain<br>
syscall-sdk is **write-enabled**: it pushes blockchain intent out to the real world<br>

```text
   [ traditional oracle ]                    [ syscall-sdk ]
     "importing reality"                   "exporting actions"

 +------------------------+            +------------------------+
 |    real world data     |            |     on-chain event     |
 | (prices, weather, rng) |            | (payment, governance)  |
 +------------------------+            +------------------------+
             |                                     |
             | input                               | 1 line of code
             v                                     v
 +------------------------+            +------------------------+
 |    standard oracle     |            |      syscall-sdk       |
 |      (chainlink)       |            |   (inversion layer)    |
 +------------------------+            +------------------------+
             |                                     |
             | data                                | action
             v                                     v
 +------------------------+            +------------------------+
 |      blockchain        |            |    real world exec     |
 |   (smart contract)     |            +------------------------+
 +------------------------+            |  > [sms / email]       |
                                       |  > [x / twitter post]  |
                                       |  > [telegram bot]      |
                                       |  > [trigger ai agent]  |
                                       +------------------------+
```

--------------------------------

## 0x02: architecture & data flow

the architecture is designed to be trustless<br>
the execution of off-chain actions (email, sms, api calls) is strictly conditioned by the cryptographic verification of the on-chain payment<br>

```text
                                                +-----------------------+                                                                 +-----------------------+
                                                |                       |                            2 pay                                |      blockchain       |
                                                |                       |---------------------------------------------------------------->|                       |
                                                |                       |                                                                 |                       |
   +-----------------------+                    |                       |                      3 transaction mined                        |                       |
   |    front-end user     |                    |                       |<----------------------------------------------------------------|                       |
   |  react, vue, next.js  |                    |                       |                                                                 |                       |
   +-----------------------+                    |                       |                    +-----------------------+                    |   syscall-contract    |
               |                                |                       |   4 sig + txhash   |                       |                    |                       |
   +-----------------------+                    |                       |------------------->|                       |                    |                       |
   |   internet browser    |                    |                       |                    |                       |                    |                       |
+->|   wallet (metamask)   |---------+          |                       |                    |                       | 5 verify payment   |                       |
|  |                       |         |          |                       |                    |                       |------------------->|                       |
|  | new syscall({signer}) |         |          |                       |                    |                       |                    |                       |
|  +-----------------------+         |          |                       |       6 jwt        |                       |                    +-----------------------+
|                                    | 1 call   |                       |<-------------------|                       |
|                                    +--------->|      syscall-sdk      |                    |                       |                    +-----------------------+
|                                    |          |                       |    7 jwt + data    |                       |                    |                       |
|  +-----------------------+         |          |                       |------------------->|                       |         +--------->|     email-gateway     |
|  |    server / script    |         |          |                       |                    |    syscall-relayer    |         |          |                       |
+->|  private key (.env)   |         |          |                       |                    |                       |         |          +-----------------------+
|  |                       |---------+          |                       |                    |                       |         |
|  | new syscall({signer}) |                    |                       |                    |                       |         |          +-----------------------+
|  +-----------------------+                    |                       |                    |                       | 8 send  |          |                       |
|              |                                |                       |                    |                       |---------+--------->|      sms-gateway      |
|  +-----------------------+                    |                       |                    |                       |         |          |                       |
|  |   backend developer   |                    |                       |                    |                       |         |          +-----------------------+
|  |     node.js, bot      |                    |                       |                    |                       |         |
|  +-----------------------+                    |                       |                    |                       |         |          +-----------------------+
|                                               |                       |       9 ack        |                       |         |          |                       |
|                                               |                       |<-------------------|                       |         +--------->|     other-gateway     |
|                                               |                       |                    |                       |                    |                       |
|                                               +-----------------------+                    +-----------------------+                    +-----------------------+
|                        10 ack                            |
+----------------------------------------------------------+

```

--------------------------------

## 0x03: roadmap & funding

we are not just writing code, we are mapping a new infrastructure<br>
this roadmap is our commitment to shipping<br>

```text
phase 1 : genesis (q1 2026) - foundation
[x] architecture proof of concept (poc)
[ ] core sdk release v0.1 (npm package)
[ ] linux & macos kernel support
[ ] first gateway integration (smtp / email)
[ ] launch discord community (early access)

phase 2 : expansion (q2 2026) - scaling
[ ] multi-chain support (ethereum, arbitrum, optimism)
[ ] new output triggers (telegram bot, openai, x/twitter)
[ ] smart contract security audit (external firm)
[ ] windows & bsd support
[ ] community raise (crowd-equity / gitcoin round)

phase 3 : autonomy (h2 2026) - decentralization
[ ] decentralized relayer network (run your own node)
[ ] governance token launch
[ ] syscall dao formation
[ ] v1.0 mainnet stability
```

--------------------------------

## 0x04: join the network

the code is live<br>
the network is forming<br>
don't get stuck in user-space<br>

```text
     _    ___    _   _   _    
    | |  / _ \  | | | \ | |   
 _  | | | | | | | | |  \| |   
| |_| | | |_| | | | | |\  |   
 \___/   \___/  |_| |_| \_|

```

### [ [ > 👾 join the discord (dev) < ] ](https://discord.gg/p3nBwNKUe7)<br>
> direct access to founders and early-adopters<br><br>

### [ [ > 📜 read the whitepaper < ] ](https://github.com/syscall-sdk/core/blob/main/docs/whitepaper.md)<br>
> detailed technical vision & tokenomics<br><br>

### [ [ > ⚡ support the project < ] ](https://github.com/syscall-sdk/core/blob/main/docs/funding.md)<br>
> become a "founding node" (early access)<br><br>
