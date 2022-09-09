// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";

/// @dev Minified wrapped ETH interface
interface IWETH is IERC20 {
    function deposit() external payable;

    function withdraw(uint256 wad) external;
}
