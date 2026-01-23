// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/proxy/Clones.sol";
import "@openzeppelin/contracts/access/Ownable.sol";
import "./syscall-heartbeat-job.sol";

/**
 * @title SyscallHeartbeatFactory
 * @notice Registry that deploys and manages user heartbeat jobs.
 * @dev Uses EIP-1167 minimal proxies for gas efficiency.
 */
contract SyscallHeartbeatFactory is Ownable {
    address public implementation; 
    address[] public allJobs;      

    mapping(address => uint256) public jobIndexes;
    mapping(address => bool) public isJob;

    // [CHANGE] Now state variables, not constants
    uint256 public minInitialDeposit;
    uint256 public solvencyThreshold;

    event JobCreated(address indexed jobAddress, address indexed owner, uint256 interval);
    event JobRemoved(address indexed jobAddress);
    event FeesWithdrawn(address indexed owner, uint256 amount);
    event ImplementationUpdated(address oldImpl, address newImpl);
    // [CHANGE] New event for settings update
    event SettingsUpdated(uint256 newMinDeposit, uint256 newSolvencyThreshold);

    constructor(address _implementation) Ownable(msg.sender) {
        require(_implementation != address(0), "Invalid implementation address");
        implementation = _implementation;
        
        // [CHANGE] Set default values as requested
        minInitialDeposit = 0.003 ether;
        solvencyThreshold = 0.001 ether;
    }

    receive() external payable {}

    function setImplementation(address _newImplementation) external onlyOwner {
        require(_newImplementation != address(0), "Invalid address");
        emit ImplementationUpdated(implementation, _newImplementation);
        implementation = _newImplementation;
    }

    /**
     * @notice Allows owner to update financial parameters dynamically.
     * @param _minDeposit New minimum deposit for creating a job.
     * @param _solvencyThreshold New threshold below which jobs are killed.
     */
    function updateSettings(uint256 _minDeposit, uint256 _solvencyThreshold) external onlyOwner {
        require(_minDeposit >= _solvencyThreshold, "Deposit must cover solvency threshold");
        minInitialDeposit = _minDeposit;
        solvencyThreshold = _solvencyThreshold;
        emit SettingsUpdated(_minDeposit, _solvencyThreshold);
    }

    function withdrawFees() external onlyOwner {
        uint256 balance = address(this).balance;
        require(balance > 0, "No fees to withdraw");
        (bool sent, ) = payable(owner()).call{value: balance}("");
        require(sent, "Withdraw failed");
        emit FeesWithdrawn(owner(), balance);
    }

    function createJob(address _target, bytes calldata _data, uint256 _intervalSeconds) external payable {
        require(_intervalSeconds > 0, "Interval must be > 0");
        require(_target != address(0), "Invalid target");
        
        // [CHANGE] Use the dynamic variable
        require(msg.value >= minInitialDeposit, "Deposit too low");

        address clone = Clones.clone(implementation);
        SyscallHeartbeatJob(payable(clone)).initialize(msg.sender, address(this), _target, _data, _intervalSeconds);

        (bool sent, ) = clone.call{value: msg.value}("");
        require(sent, "Failed to transfer initial credit");

        jobIndexes[clone] = allJobs.length; 
        allJobs.push(clone);
        isJob[clone] = true;
        
        emit JobCreated(clone, msg.sender, _intervalSeconds);
    }

    function removeJob() external {
        address jobToRemove = msg.sender;
        require(isJob[jobToRemove], "Unauthorized");

        uint256 indexToDelete = jobIndexes[jobToRemove];
        uint256 lastIndex = allJobs.length - 1;

        if (indexToDelete != lastIndex) {
            address lastJob = allJobs[lastIndex];
            allJobs[indexToDelete] = lastJob;      
            jobIndexes[lastJob] = indexToDelete;   
        }

        allJobs.pop();                   
        delete jobIndexes[jobToRemove];  
        delete isJob[jobToRemove];       

        emit JobRemoved(jobToRemove);
    }

    function getJobs() external view returns (address[] memory) {
        return allJobs;
    }
}
