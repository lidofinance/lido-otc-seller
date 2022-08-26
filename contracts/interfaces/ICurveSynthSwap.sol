// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

/// @title Minified Curve router interface
interface ICurveSynthSwap {
    function get_estimated_swap_amount(
        address from,
        address to,
        uint256 amount
    ) external view returns (uint256);
}
