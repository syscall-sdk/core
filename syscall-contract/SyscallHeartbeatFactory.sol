// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/proxy/Clones.sol";
import "@openzeppelin/contracts/access/Ownable.sol";
import "./SyscallHeartbeatJob.sol";

/**
 * @title SyscallHeartbeatFactory
 * @notice Registry that deploys and manages user heartbeat jobs.
 * @dev Uses EIP-1167 minimal proxies for gas efficiency.
 * Secure against pollution attacks via MIN_INITIAL_DEPOSIT.
 */
contract SyscallHeartbeatFactory is Ownable {
    address public implementation; 
    address[] public allJobs;      

    // Efficient mapping for O(1) removal logic
    mapping(address => uint256) public jobIndexes;
    // Security mapping to verify calls come from legitimate jobs
    mapping(address => bool) public isJob;

    // SECURITY: Minimum deposit required to prevent spam/dust contracts
    // Must match or exceed the SOLVENCY_THRESHOLD of the Job contract (0.002 ether)
    uint256 public constant MIN_INITIAL_DEPOSIT = 0.002 ether;

    event JobCreated(address indexed jobAddress, address indexed owner, uint256 interval);
    event JobRemoved(address indexed jobAddress);
    event FeesWithdrawn(address indexed owner, uint256 amount);
    event ImplementationUpdated(address oldImpl, address newImpl);

    constructor(address _implementation) Ownable(msg.sender) {
        require(_implementation != address(0), "Invalid implementation address");
        implementation = _implementation;
    }

    /**
     * @notice Allows the Factory to receive the 1% fee from User Jobs.
     */
    receive() external payable {}

    /**
     * @notice Updates the master implementation address (onlyOwner).
     * @dev Allows upgrading logic for FUTURE jobs (existing jobs remain on old logic).
     */
    function setImplementation(address _newImplementation) external onlyOwner {
        require(_newImplementation != address(0), "Invalid address");
        emit ImplementationUpdated(implementation, _newImplementation);
        implementation = _newImplementation;
    }

    /**
     * @notice Withdraws all accumulated fees to the factory owner.
     * @dev Protected by onlyOwner to prevent theft.
     */
    function withdrawFees() external onlyOwner {
        uint256 balance = address(this).balance;
        require(balance > 0, "No fees to withdraw");

        // Use .call to avoid gas limit issues on transfers
        (bool sent, ) = payable(owner()).call{value: balance}("");
        require(sent, "Withdraw failed");

        emit FeesWithdrawn(owner(), balance);
    }

    /**
     * @notice Deploys a new Heartbeat Job for a user.
     * @param _target The contract address to call.
     * @param _data The function signature and arguments encoded.
     * @param _intervalSeconds Minimum time (in seconds) between executions.
     */
    function createJob(address _target, bytes calldata _data, uint256 _intervalSeconds) external payable {
        require(_intervalSeconds > 0, "Interval must be > 0");
        require(_target != address(0), "Invalid target");
        
        // SECURITY CHECK: Prevent creation of insolvent jobs (Dust Spam Protection)
        require(msg.value >= MIN_INITIAL_DEPOSIT, "Deposit too low: Must cover initial solvency");

        // 1. Deploy Clone (EIP-1167)
        address clone = Clones.clone(implementation);
        
        // 2. Initialize Clone (Atomic operation in the same tx -> Prevents Front-Running)
        SyscallHeartbeatJob(payable(clone)).initialize(msg.sender, address(this), _target, _data, _intervalSeconds);
        
        // 3. Forward Initial Credit
        // Safe to transfer because we verified msg.value >= MIN_INITIAL_DEPOSIT
        (bool sent, ) = clone.call{value: msg.value}("");
        require(sent, "Failed to transfer initial credit");

        // 4. Register Job
        jobIndexes[clone] = allJobs.length; 
        allJobs.push(clone);
        isJob[clone] = true;
        
        emit JobCreated(clone, msg.sender, _intervalSeconds);
    }

    /**
     * @notice Removes a job from the registry. Can only be called by the Job itself.
     * @dev Uses Swap-and-Pop to ensure O(1) gas cost regardless of registry size.
     */
    function removeJob() external {
        address jobToRemove = msg.sender;
        
        // SECURITY: Only a registered job can remove itself
        require(isJob[jobToRemove], "Unauthorized: Caller is not a registered job");

        uint256 indexToDelete = jobIndexes[jobToRemove];
        uint256 lastIndex = allJobs.length - 1;

        // If the job to remove is not the last one, swap it with the last one
        if (indexToDelete != lastIndex) {
            address lastJob = allJobs[lastIndex];
            allJobs[indexToDelete] = lastJob;      // Move last job to the hole
            jobIndexes[lastJob] = indexToDelete;   // Update index of the moved job
        }

        allJobs.pop();                   // Remove the last element
        delete jobIndexes[jobToRemove];  // Clean map
        delete isJob[jobToRemove];       // Clean map

        emit JobRemoved(jobToRemove);
    }

    /**
     * @notice Returns the list of all active jobs.
     */
    function getJobs() external view returns (address[] memory) {
        return allJobs;
    }
}
