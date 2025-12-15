// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

// Standard OpenZeppelin import for access control
import "@openzeppelin/contracts/access/Ownable.sol";

/**
 * @title syscall-contract
 * @dev Payment gateway contract for the syscall-sdk (Reverse Oracle).
 * Handles dynamic pricing for services and emits payment proofs.
 */
contract syscall-contract is Ownable {

    // --- Storage ---
    // Mapping for the unlimited price catalog.
    // Key (string) = Service name (e.g., "SMS")
    // Value (uint256) = Price in Wei
    mapping(string => uint256) public tariffs;

    // --- Events (For off-chain verification) ---
    // This event allows anyone (Relayer/User) to verify:
    // - Who paid (user)
    // - What service (service)
    // - How much (amount)
    // - When (timestamp)
    event ActionPaid(
        address indexed user, 
        string service, 
        uint256 amount, 
        uint256 timestamp
    );

    event TariffUpdated(string service, uint256 price);
    event TariffDeleted(string service);

    // --- Initialization ---
    // The constructor sets the deployer as the initial owner.
    // No tariffs are defined at creation, as requested.
    constructor() Ownable(msg.sender) {
        // Catalog starts empty.
    }

    // =============================================================
    // PUBLIC FUNCTIONS (For Users / SDK)
    // =============================================================

    /**
     * @notice Allows a user to pay for an off-chain service.
     * @param service The name of the service (e.g., "SMS").
     * @dev Emits the ActionPaid event which is indexed by the syscall-relayer.
     */
    function pay(string calldata service) external payable {
        uint256 price = tariffs[service];

        // Verify if the service exists/is active (price > 0)
        require(price > 0, "syscall-contract: service unknown or inactive");
        
        // Verify the sent amount
        require(msg.value >= price, "syscall-contract: insufficient payment");

        // Emit payment proof (stored in blockchain logs)
        emit ActionPaid(msg.sender, service, msg.value, block.timestamp);
    }

    // =============================================================
    // ADMIN FUNCTIONS (Owner only)
    // =============================================================

    /**
     * @notice Create or update a tariff.
     * @param service Service name (e.g., "EMAIL").
     * @param price Price in Wei (e.g., 0.001 ether).
     */
    function setTariff(string calldata service, uint256 price) external onlyOwner {
        require(price > 0, "Price must be greater than 0");
        tariffs[service] = price;
        emit TariffUpdated(service, price);
    }

    /**
     * @notice Remove a tariff from the catalog.
     * @param service Service name to remove.
     */
    function deleteTariff(string calldata service) external onlyOwner {
        delete tariffs[service];
        emit TariffDeleted(service);
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

    // Note: Admin wallet management is handled natively by Ownable via `transferOwnership(newOwner)`.
}
