// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/access/Ownable.sol";

/**
 * @title SyscallContract
 * @dev Payment gateway with per-character billing and anti-replay.
 */
contract SyscallContract is Ownable {

    // --- Storage ---
    // Service catalog (e.g., "SMS" => 0.001 ETH per char)
    mapping(string => uint256) public services;
    
    uint256 public nextPaymentId;
    mapping(uint256 => bool) public isConsumed;

    // --- Events ---
    event ActionPaid(
        uint256 indexed paymentId, 
        address indexed user, 
        string name, 
        uint256 amount, 
        uint256 quantity,   // <--- Added: Number of characters paid for
        uint256 timestamp
    );

    event ActionConsumed(uint256 indexed paymentId, uint256 timestamp);
    event ServiceUpdated(string name, uint256 price);
    event ServiceDeleted(string name);

    constructor() Ownable(msg.sender) {}

    // =============================================================
    // PUBLIC FUNCTIONS
    // =============================================================

    /**
     * @notice Allows a user to pay for an off-chain service based on length.
     * @param name The name of the service (e.g., "SMS").
     * @param quantity The length of the message (number of characters/bytes).
     */
    function pay(string calldata name, uint256 quantity) external payable {
        uint256 unitPrice = services[name];
        
        require(unitPrice > 0, "Syscall: Service unknown or inactive");
        require(quantity > 0, "Syscall: Quantity must be greater than 0");

        // Calculate total cost: Price Per Char * Number of Chars
        uint256 totalCost = unitPrice * quantity;

        require(msg.value >= totalCost, "Syscall: Insufficient payment for this length");

        uint256 paymentId = nextPaymentId;
        nextPaymentId++;

        // Emit event with the quantity so the Relayer can verify limit
        emit ActionPaid(paymentId, msg.sender, name, msg.value, quantity, block.timestamp);
    }

    // =============================================================
    // ADMIN & RELAYER FUNCTIONS
    // =============================================================

    function consumePayment(uint256 paymentId) external onlyOwner {
        require(paymentId < nextPaymentId, "Syscall: Invalid payment ID");
        require(!isConsumed[paymentId], "Syscall: Payment already consumed");
        
        isConsumed[paymentId] = true;
        emit ActionConsumed(paymentId, block.timestamp);
    }

    function setService(string calldata name, uint256 price) external onlyOwner {
        require(price > 0, "Price must be greater than 0");
        services[name] = price;
        emit ServiceUpdated(name, price);
    }

    function deleteService(string calldata name) external onlyOwner {
        delete services[name];
        emit ServiceDeleted(name);
    }

    function withdrawTo(address payable recipient) external onlyOwner {
        require(recipient != address(0), "Invalid recipient address");
        uint256 balance = address(this).balance;
        require(balance > 0, "No funds to withdraw");
        (bool success, ) = recipient.call{value: balance}("");
        require(success, "Transfer failed");
    }
}
