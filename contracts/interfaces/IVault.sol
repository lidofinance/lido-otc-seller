// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

/// @dev Minified Aragon Agent (Vault) interface
interface IVault {
    function deposit(address _token, uint256 _value) external payable;
}
