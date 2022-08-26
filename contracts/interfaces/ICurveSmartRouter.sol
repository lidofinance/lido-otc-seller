// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

/// @title Minified Curve router interface
interface ICurveSmartRouter {
    function get_exchange_routing(
        address from,
        address to,
        uint256 amount
    ) external view returns (address[6] memory, uint256[8] memory, uint256);
}
