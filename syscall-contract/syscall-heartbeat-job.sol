// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

// [CHANGE] Extended interface to read settings from Factory
interface IFactory {
    function removeJob() external;
    function solvencyThreshold() external view returns (uint256);
}

/**
 * @title SyscallHeartbeatJob
 * @notice Individual user contract that holds funds and pays for execution.
 * @dev Designed to be deployed as a minimal proxy (clone).
 */
contract SyscallHeartbeatJob {
    address public owner;
    address public factory;
    address public targetContract;
    bytes public data;
    uint256 public interval; 
    uint256 public lastRun;
    
    uint256 constant GAS_OVERHEAD = 45000; 

    // [CHANGE] Removed constant SOLVENCY_THRESHOLD. 
    // It is now fetched dynamically from the factory.

    uint256 constant RUNNER_PERCENT = 101; 
    uint256 constant FACTORY_PERCENT = 1;  

    bool private initialized;

    function initialize(
        address _owner, 
        address _factory, 
        address _targetContract,
        bytes memory _data,
        uint256 _interval
    ) external {
        require(!initialized, "Already initialized");
        owner = _owner;
        factory = _factory;
        targetContract = _targetContract;
        data = _data;
        interval = _interval;
        initialized = true;
    }

    receive() external payable {}

    function executeTask() external {
        uint256 startGas = gasleft();

        require(block.timestamp >= lastRun + interval, "Too early");
        
        // [CHANGE] Check solvency based on current ETH balance vs basically 0
        // We do the strict check at the end anyway.
        require(address(this).balance > 0, "Empty balance");

        lastRun = block.timestamp;

        (bool success, ) = targetContract.call(data);
        if (success) {} 

        uint256 gasUsed = startGas - gasleft();
        uint256 totalGas = gasUsed + GAS_OVERHEAD;
        uint256 baseCost = totalGas * tx.gasprice;

        uint256 runnerPayment = (baseCost * RUNNER_PERCENT) / 100;
        uint256 factoryPayment = (baseCost * FACTORY_PERCENT) / 100;
        uint256 totalBill = runnerPayment + factoryPayment;

        require(address(this).balance >= totalBill, "Not enough funds to pay bill");

        uint256 remainingBalance = address(this).balance - totalBill;

        // [CHANGE] Fetch dynamic threshold from Factory
        uint256 dynamicThreshold = IFactory(factory).solvencyThreshold();

        if (remainingBalance < dynamicThreshold) {
            // --- END OF LIFE ---
            IFactory(factory).removeJob();
            
            if (remainingBalance > 0) {
                payable(owner).transfer(remainingBalance);
            }
            
            payable(msg.sender).transfer(address(this).balance);
            
        } else {
            // --- NORMAL OPERATION ---
            payable(msg.sender).transfer(runnerPayment);
            
            (bool sent, ) = factory.call{value: factoryPayment}("");
            require(sent, "Factory fee transfer failed");
        }
    }
    
    function withdraw() external {
        require(msg.sender == owner, "Not the owner");
        IFactory(factory).removeJob();
        payable(owner).transfer(address(this).balance);
    }
}
