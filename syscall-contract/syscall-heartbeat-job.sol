// SPDX-License-Identifier: MIT
pragma solidity 0.8.33;

interface IFactory {
    function removeJob() external;
    // Updated Interface to expect 5 return values
    function getGasSettings() external view returns (uint256, uint256, uint256, uint256, uint256);
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
        require(address(this).balance > 0, "Empty balance");

        // Fetch current settings from Factory
        // Note the trailing comma to ignore the 5th value (minInitialDepositGas)
        (
            uint256 overhead, 
            uint256 relayerFee, 
            uint256 factoryFee, 
            uint256 solvencyThresholdGas,
            
        ) = IFactory(factory).getGasSettings();

        // [STEP 1 & 2] PRE-EXECUTION SOLVENCY CHECK
        uint256 threshold = solvencyThresholdGas * tx.gasprice;
        
        if (address(this).balance < threshold) {
            IFactory(factory).removeJob();
            (bool sentRelayer, ) = payable(msg.sender).call{value: address(this).balance}("");
            require(sentRelayer, "Relayer sweep failed");
            return; // Exit transaction here
        }

        // [STEP 3] EXECUTION
        lastRun = block.timestamp;
        (bool success, ) = targetContract.call(data);
        if (success) {} 

        // Calculation
        uint256 gasUsed = startGas - gasleft();
        uint256 totalGas = gasUsed + overhead;

        uint256 runnerPayment = (totalGas + relayerFee) * tx.gasprice;
        uint256 factoryPayment = factoryFee * tx.gasprice;
        uint256 totalBill = runnerPayment + factoryPayment;

        // [STEP 4 & 5] POST-EXECUTION PAYMENT OR LIQUIDATION
        
        if (address(this).balance < totalBill) {
            // Case A: Cannot afford the bill -> Force Liquidation
            IFactory(factory).removeJob();
            (bool sentRelayer, ) = payable(msg.sender).call{value: address(this).balance}("");
            require(sentRelayer, "Relayer sweep failed");

        } else {
            uint256 remainingBalance = address(this).balance - totalBill;

            if (remainingBalance < threshold) {
                // Case B: Not enough funds for FUTURE safety -> Force Liquidation
                IFactory(factory).removeJob();
                (bool sentRelayer, ) = payable(msg.sender).call{value: address(this).balance}("");
                require(sentRelayer, "Relayer sweep failed");
            } else {
                // Case C: Healthy -> Normal Payment
                (bool sentRunner, ) = payable(msg.sender).call{value: runnerPayment}("");
                require(sentRunner, "Runner payment failed");

                (bool sentFactory, ) = factory.call{value: factoryPayment}("");
                require(sentFactory, "Factory fee transfer failed");
            }
        }
    }
    
    function withdraw() external {
        require(msg.sender == owner, "Not the owner");
        IFactory(factory).removeJob();
        
        // Manual withdraw sends funds to Owner
        (bool sent, ) = payable(owner).call{value: address(this).balance}("");
        require(sent, "Withdraw failed");
    }
}
