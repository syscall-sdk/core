// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/access/Ownable.sol";

/**
 * @title SyscallContract
 * @dev Payment gateway using Commit-Reveal scheme.
 */
contract SyscallContract is Ownable {

    mapping(string => uint256) public services;
    uint256 public nextPaymentId;
    mapping(uint256 => bool) public isConsumed;

    // --- Updated Event with Commitment ---
    event ActionPaid(
        uint256 indexed paymentId, 
        address indexed user, 
        string name, 
        uint256 amount, 
        uint256 quantity,
        bytes32 commitment, // <--- NEW: Hash of the secret
        uint256 timestamp
    );

    event ActionConsumed(uint256 indexed paymentId, uint256 timestamp);
    event ServiceUpdated(string name, uint256 price);
    event ServiceDeleted(string name);

    constructor() Ownable(msg.sender) {}

    // --- Updated Pay Function ---
    function pay(string calldata name, uint256 quantity, bytes32 commitment) external payable {
        uint256 unitPrice = services[name];
        require(unitPrice > 0, "Syscall: Service unknown or inactive");
        require(quantity > 0, "Syscall: Quantity must be greater than 0");
        require(commitment != bytes32(0), "Syscall: Commitment required");

        uint256 totalCost = unitPrice * quantity;
        require(msg.value >= totalCost, "Syscall: Insufficient payment");

        uint256 paymentId = nextPaymentId;
        nextPaymentId++;

        emit ActionPaid(paymentId, msg.sender, name, msg.value, quantity, commitment, block.timestamp);
    }

    // --- Admin Functions ---
    function consumePayment(uint256 paymentId) external onlyOwner {
        require(paymentId < nextPaymentId, "Syscall: Invalid payment ID");
        require(!isConsumed[paymentId], "Syscall: Payment already consumed");
        
        isConsumed[paymentId] = true;
        emit ActionConsumed(paymentId, block.timestamp);
    }

    function setService(string calldata name, uint256 price) external onlyOwner {
        services[name] = price;
        emit ServiceUpdated(name, price);
    }

    function deleteService(string calldata name) external onlyOwner {
        delete services[name];
        emit ServiceDeleted(name);
    }

    function withdrawTo(address payable recipient) external onlyOwner {
        require(recipient != address(0), "Invalid recipient");
        (bool success, ) = recipient.call{value: address(this).balance}("");
        require(success, "Transfer failed");
    }
}
