// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

/// @dev Minified wrapped ETH interface
interface IOTCRegistry {
    function getPriceAndMaxSlippage(address sellToken, address buyToken) external view returns (uint256 price, uint16 slippage);
}
