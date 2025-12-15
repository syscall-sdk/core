// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

// Standard OpenZeppelin import for access control
import "@openzeppelin/contracts/access/Ownable.sol";

/**
 * @title SyscallContract
 * @dev Payment gateway contract for the syscall-sdk (reverse oracle).
 * Handles dynamic pricing and emits payment proofs.
 */
contract SyscallContract is Ownable {

    // --- Storage ---
    // Mapping for the unlimited service catalog.
    // Key (string) = name (e.g., "SMS")
    // Value (uint256) = price in Wei
    mapping(string => uint256) public services;

    // --- Events (For off-chain verification) ---
    // This event allows anyone (Relayer/User) to verify:
    // - Who paid (user)
    // - What name (name)
    // - How much (amount)
    // - When (timestamp)
    event ActionPaid(
        address indexed user, 
        string name, 
        uint256 amount, 
        uint256 timestamp
    );

    event ServiceUpdated(string name, uint256 price);
    event ServiceDeleted(string name);

    // --- Initialization ---
    // The constructor sets the deployer as the initial owner.
    // No services are defined at creation, as requested.
    constructor() Ownable(msg.sender) {
        // Catalog starts empty.
    }

    // =============================================================
    // PUBLIC FUNCTIONS (For Users / SDK)
    // =============================================================

    /**
     * @notice Allows a user to pay for an off-chain service.
     * @param name The name of the service (e.g., "SMS").
     * @dev Emits the ActionPaid event which is indexed by syscall-relayer.
     */
    function pay(string calldata name) external payable {
        uint256 price = services[name];

        // Verify if the service exists/is active (price > 0)
        require(price > 0, "Syscall: Service unknown or inactive");
        
        // Verify the sent amount
        require(msg.value >= price, "Syscall: Insufficient payment");

        // Emit payment proof (stored in blockchain logs)
        emit ActionPaid(msg.sender, name, msg.value, block.timestamp);
    }

    // =============================================================
    // ADMIN FUNCTIONS (Owner only)
    // =============================================================

    /**
     * @notice Create or update a service price.
     * @param name Service name (e.g., "EMAIL").
     * @param price Price in Wei (e.g., 0.001 ether).
     */
    function setService(string calldata name, uint256 price) external onlyOwner {
        require(price > 0, "Price must be greater than 0");
        services[name] = price;
        emit ServiceUpdated(name, price);
    }

    /**
     * @notice Remove a service from the catalog.
     * @param name Service name to remove.
     */
    function deleteService(string calldata name) external onlyOwner {
        delete services[name];
        emit ServiceDeleted(name);
    }

    /**
     * @notice Withdraw contract funds to a specific wallet.
     * @param recipient The address that will receive the funds.
     */
    function withdrawTo(address payable recipient) external onlyOwner {
        require(recipient != address(0), "Invalid recipient address");
        uint256 balance = address(this).balance;
        require(balance > 0, "No funds to withdraw");

        (bool success, ) = recipient.call{value: balance}("");
        require(success, "Transfer failed");
    }
}
