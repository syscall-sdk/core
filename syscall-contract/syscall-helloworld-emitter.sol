// SPDX-License-Identifier: MIT
pragma solidity ^0.8.33;

/**
 * @title SyscallHelloworldEmitter
 * @dev Simple contract to demonstrate event emission.
 */
contract HelloWorldEmitter {
    // Event declaration
    event MessageEmitted(string message);

    /**
     * @notice Emits a "Hello World" event.
     */
    function sayHello() external {
        emit MessageEmitted("Hello World");
    }
}
