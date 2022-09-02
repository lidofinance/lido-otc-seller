// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

/// @dev Minified wrapped ETH interface
interface IWETH {
    function deposit() external payable;

    function withdraw(uint256 wad) external;
}
