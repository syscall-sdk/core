// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

interface IFactory {
    function removeJob() external;
}

/**
 * @title SyscallHeartbeatJob
 * @notice Individual user contract that holds funds and pays for execution.
 * @dev Designed to be deployed as a minimal proxy (clone).
 */
contract SyscallHeartbeatJob {
    address public owner;
    address public factory;
    address public target;
    bytes public data;
    
    uint256 public interval; 
    uint256 public lastRun;
    
    // Gas overhead covers: Base Tx (21k) + 2 Transfers + Logic (~45k safe margin)
    // Ensures the bot is reimbursed for the logic cost, not just the task cost.
    uint256 constant GAS_OVERHEAD = 45000; 
    
    // Solvency Threshold: If balance drops below this, the job self-terminates.
    // Matches Factory's MIN_INITIAL_DEPOSIT.
    uint256 constant SOLVENCY_THRESHOLD = 0.002 ether; 

    // FEE STRUCTURE
    uint256 constant RUNNER_PERCENT = 101; // Bot gets 101% (1% pure profit)
    uint256 constant FACTORY_PERCENT = 1;  // Factory gets 1% fee

    bool private initialized;

    /**
     * @notice Initializes the clone. Can only be called once by the Factory.
     */
    function initialize(
        address _owner, 
        address _factory, 
        address _target, 
        bytes memory _data,
        uint256 _interval
    ) external {
        // SECURITY: Prevents re-initialization attack
        require(!initialized, "Already initialized");
        
        owner = _owner;
        factory = _factory;
        target = _target;
        data = _data;
        interval = _interval;
        initialized = true;
    }

    /**
     * @notice Allows the contract to receive ETH (Top-up credit).
     */
    receive() external payable {}

    /**
     * @notice The main function called by runBots.
     * @dev Permissionless: Anyone can call this if the time condition is met.
     */
    function executeTask() external {
        uint256 startGas = gasleft();

        // 1. Validation
        require(block.timestamp >= lastRun + interval, "Too early");
        require(address(this).balance > 0.001 ether, "Insolvent");

        // 2. CEI Pattern (Checks-Effects-Interactions): 
        // Update state BEFORE external call to prevent reentrancy attacks.
        lastRun = block.timestamp;

        // 3. Execute User Task
        // We use low-level .call so the bot gets paid even if the user's logic fails/reverts.
        (bool success, ) = target.call(data);
        // Note: We intentionally ignore 'success'. The service is "attempting the call".
        
        // 4. Calculate Bill
        uint256 gasUsed = startGas - gasleft();
        uint256 totalGas = gasUsed + GAS_OVERHEAD;
        uint256 baseCost = totalGas * tx.gasprice;

        uint256 runnerPayment = (baseCost * RUNNER_PERCENT) / 100;
        uint256 factoryPayment = (baseCost * FACTORY_PERCENT) / 100;
        uint256 totalBill = runnerPayment + factoryPayment;
        
        require(address(this).balance >= totalBill, "Not enough funds to pay bill");

        // 5. Solvency Check & Cleanup (Zombie Killer Logic)
        uint256 remainingBalance = address(this).balance - totalBill;

        if (remainingBalance < SOLVENCY_THRESHOLD) {
            // --- END OF LIFE: Clean up ---
            
            // A. Remove from factory registry
            IFactory(factory).removeJob();
            
            // B. Return dust (remaining small amount) to owner
            if (remainingBalance > 0) {
                payable(owner).transfer(remainingBalance);
            }
            
            // C. Pay the runner with whatever is left (Total Balance)
            // Prioritize paying the runner over the factory fee in this death scenario
            payable(msg.sender).transfer(address(this).balance);
            
        } else {
            // --- NORMAL OPERATION ---
            
            // Pay the Bot (101%)
            payable(msg.sender).transfer(runnerPayment);
            
            // Pay the Factory (1%)
            // Use .call to prevent DOS if factory logic consumes too much gas
            (bool sent, ) = factory.call{value: factoryPayment}("");
            require(sent, "Factory fee transfer failed");
        }
    }
    
    /**
     * @notice Allows owner to cancel the job and retrieve funds.
     */
    function withdraw() external {
        // SECURITY: Prevents theft of funds by third parties
        require(msg.sender == owner, "Not the owner");
        
        // 1. Remove from factory registry first
        IFactory(factory).removeJob();
        
        // 2. Return all funds to owner
        payable(owner).transfer(address(this).balance);
    }
}
