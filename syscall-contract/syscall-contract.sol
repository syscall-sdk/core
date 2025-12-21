// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/access/Ownable.sol";

/**
 * @title SyscallContract
 * @dev Payment gateway with anti-replay protection.
 * The Python script (Relayer) must use the Owner wallet to validate consumption.
 */
contract SyscallContract is Ownable {

    // --- Storage ---
    
    // Service catalog (e.g., "SMS" => 0.001 ETH)
    mapping(string => uint256) public services;

    // Counter to generate a unique ID for every payment transaction
    uint256 public nextPaymentId;

    // Consumption tracking: ID => has the service been delivered?
    mapping(uint256 => bool) public isConsumed;

    // --- Events ---

    // Emitted when a user pays via blockchain
    event ActionPaid(
        uint256 indexed paymentId, // Unique ID essential for tracking
        address indexed user, 
        string name, 
        uint256 amount, 
        uint256 timestamp
    );

    // Emitted when the Relayer (Owner) confirms the service is delivered
    event ActionConsumed(uint256 indexed paymentId, uint256 timestamp);

    event ServiceUpdated(string name, uint256 price);
    event ServiceDeleted(string name);

    // --- Initialization ---
    constructor() Ownable(msg.sender) {
        // The contract deployer is the default Owner.
    }

    // =============================================================
    // PUBLIC FUNCTIONS (For Users)
    // =============================================================

    /**
     * @notice Allows a user to pay for an off-chain service.
     * @param name The name of the service (e.g., "SMS").
     */
    function pay(string calldata name) external payable {
        uint256 price = services[name];
        
        // Basic checks
        require(price > 0, "Syscall: Service unknown or inactive");
        require(msg.value >= price, "Syscall: Insufficient payment");

        // Generate unique ID
        uint256 paymentId = nextPaymentId;
        nextPaymentId++;

        // Emit event with the unique ID so the Python script can track it
        emit ActionPaid(paymentId, msg.sender, name, msg.value, block.timestamp);
    }

    // =============================================================
    // ADMIN & RELAYER FUNCTIONS (Owner only)
    // =============================================================

    /**
     * @notice Marks a payment as "consumed" (service delivered).
     * @dev Only the Owner (acting as Relayer) can call this function.
     * @param paymentId The unique ID of the payment to validate.
     */
    function consumePayment(uint256 paymentId) external onlyOwner {
        // 1. Check if ID exists
        require(paymentId < nextPaymentId, "Syscall: Invalid payment ID");

        // 2. Check if already used
        require(!isConsumed[paymentId], "Syscall: Payment already consumed");

        // 3. Mark as consumed
        isConsumed[paymentId] = true;

        // 4. Confirm action on-chain
        emit ActionConsumed(paymentId, block.timestamp);
    }

    // --- Catalog Management ---

    function setService(string calldata name, uint256 price) external onlyOwner {
        require(price > 0, "Price must be greater than 0");
        services[name] = price;
        emit ServiceUpdated(name, price);
    }

    function deleteService(string calldata name) external onlyOwner {
        delete services[name];
        emit ServiceDeleted(name);
    }

    // --- Fund Management ---

    function withdrawTo(address payable recipient) external onlyOwner {
        require(recipient != address(0), "Invalid recipient address");
        uint256 balance = address(this).balance;
        require(balance > 0, "No funds to withdraw");

        (bool success, ) = recipient.call{value: balance}("");
        require(success, "Transfer failed");
    }
}
