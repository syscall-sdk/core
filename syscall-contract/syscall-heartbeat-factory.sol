// SPDX-License-Identifier: MIT
pragma solidity 0.8.33;

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

    // --- Dynamic Gas Configuration (Modifiable by Owner) ---
    uint256 public gasOverhead;
    uint256 public relayerFeeGas;
    uint256 public factoryFeeGas;
    uint256 public solvencyThresholdGas;
    uint256 public minInitialDepositGas;

    event JobCreated(address indexed jobAddress, address indexed owner, uint256 interval);
    event JobRemoved(address indexed jobAddress);
    event FeesWithdrawn(address indexed owner, uint256 amount);
    event ImplementationUpdated(address oldImpl, address newImpl);
    event GasSettingsUpdated(uint256 overhead, uint256 relayerFee, uint256 factoryFee, uint256 solvencyThreshold, uint256 minInitialDeposit);

    constructor() Ownable(msg.sender) {
        implementation = address(new SyscallHeartbeatJob());
        
        // Initialize default values
        gasOverhead = 100000;
        relayerFeeGas = 50000;
        factoryFeeGas = 20000;
        solvencyThresholdGas = 300000;
        minInitialDepositGas = 1000000000;
    }

    receive() external payable {}

    function setImplementation(address _newImplementation) external onlyOwner {
        require(_newImplementation != address(0), "Invalid address");
        emit ImplementationUpdated(implementation, _newImplementation);
        implementation = _newImplementation;
    }

    // [WRITE] Single function to update ALL gas settings
    function updateGasSettings(
        uint256 _gasOverhead, 
        uint256 _relayerFeeGas, 
        uint256 _factoryFeeGas, 
        uint256 _solvencyThresholdGas,
        uint256 _minInitialDepositGas
    ) external onlyOwner {
        gasOverhead = _gasOverhead;
        relayerFeeGas = _relayerFeeGas;
        factoryFeeGas = _factoryFeeGas;
        solvencyThresholdGas = _solvencyThresholdGas;
        minInitialDepositGas = _minInitialDepositGas;
        
        emit GasSettingsUpdated(_gasOverhead, _relayerFeeGas, _factoryFeeGas, _solvencyThresholdGas, _minInitialDepositGas);
    }

    // [READ] Single function to read ALL gas settings
    // Returns 5 values now (added minInitialDepositGas at the end)
    function getGasSettings() external view returns (uint256, uint256, uint256, uint256, uint256) {
        return (gasOverhead, relayerFeeGas, factoryFeeGas, solvencyThresholdGas, minInitialDepositGas);
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
        
        // Use the state variable directly for logic check
        uint256 requiredDeposit = minInitialDepositGas * tx.gasprice;
        require(msg.value >= requiredDeposit, "Deposit too low");

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
