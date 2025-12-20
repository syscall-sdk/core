// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

// Standard OpenZeppelin import for access control
import "@openzeppelin/contracts/access/Ownable.sol";

/**
 * @title SyscallAddressRegistry
 * @dev The "Address Resolver" for the Syscall SDK.
 * This contract acts as a permanent directory. The SDK queries this contract
 * to find the current address of the active SyscallContract.
 */
contract SyscallAddressRegistry is Ownable {

    // --- Storage ---
    // Stores the address of the current active SyscallContract (Logic/Payment)
    address public syscallContract;

    // --- Events ---
    // Emitted when the owner updates the reference to the SyscallContract
    event SyscallContractUpdated(address indexed oldAddress, address indexed newAddress);

    // --- Initialization ---
    constructor() Ownable(msg.sender) {
        // Initially empty. The owner must call setSyscallContract after deployment.
    }

    // =============================================================
    // ADMIN FUNCTIONS (Owner only)
    // =============================================================

    /**
     * @notice Update the address of the active SyscallContract.
     * @dev Only the owner can call this function.
     * @param _newAddress The address of the new SyscallContract deployed.
     */
    function setSyscallContract(address _newAddress) external onlyOwner {
        require(_newAddress != address(0), "SyscallRegistry: Invalid address (0x0)");
        
        address oldAddress = syscallContract;
        syscallContract = _newAddress;

        emit SyscallContractUpdated(oldAddress, _newAddress);
    }

    // Note: The function to change the Registry Owner is natively available 
    // via the inherited `transferOwnership(address newOwner)` function.
}
