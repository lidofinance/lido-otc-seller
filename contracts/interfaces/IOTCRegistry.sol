// SPDX-FileCopyrightText: 2022 Lido <info@lido.fi>
// SPDX-License-Identifier: MIT
pragma solidity 0.8.10;

/// @dev Minified OTCFactory interface
interface IOTCFactory {
    function getPriceAndMaxMargin(address sellToken, address buyToken) external view returns (uint256 price, uint16 priceMargin);
}
