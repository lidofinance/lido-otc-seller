// SPDX-FileCopyrightText: 2022 Lido <info@lido.fi>
// SPDX-License-Identifier: MIT
pragma solidity 0.8.10;

import {OTCSeller} from "./OTCSeller.sol";
import {Clones} from "./lib/Clones.sol";
import {LibTokenPair} from "./lib/LibTokenPair.sol";
import {IChainlinkPriceFeedV3} from "./interfaces/IChainlinkPriceFeedV3.sol";

contract OTCFactory {
    event SellerCreated(address indexed token0, address indexed token1, address indexed beneficiary, address pair);

    address public immutable implementation;

    constructor(
        address wethAddress,
        address daoVaultAddress // address beneficiaryAddress
    ) {
        implementation = address(new OTCSeller(wethAddress, daoVaultAddress));
    }

    function isSellerExists(address seller) public view returns (bool) {
        return seller.code.length > 0;
    }

    /// @dev calculates the Clone address for a pair
    function getSellerFor(
        address beneficiary,
        address tokenA,
        address tokenB
    ) external view returns (address seller) {
        (address token0, address token1) = LibTokenPair.sortTokens(tokenA, tokenB);
        bytes32 salt = keccak256(abi.encodePacked(beneficiary, token0, token1));
        seller = Clones.predictDeterministicAddress(implementation, salt, address(this));
    }

    /// @dev create the Clone for implementation and initialize it
    function createSeller(
        address beneficiary,
        address tokenA,
        address tokenB,
        address priceFeed,
        uint16 maxMargin,
        uint256 constantPrice
    ) external returns (address seller) {
        (address token0, address token1) = LibTokenPair.sortTokens(tokenA, tokenB);
        bytes32 salt = keccak256(abi.encodePacked(beneficiary, token0, token1));
        seller = Clones.predictDeterministicAddress(implementation, salt, address(this));

        require(!isSellerExists(seller), "Seller exists");

        require(seller == Clones.cloneDeterministic(implementation, salt), "Wrong clone address");
        OTCSeller(payable(seller)).initialize(beneficiary, tokenA, tokenB, priceFeed, maxMargin, constantPrice);
        emit SellerCreated(token0, token1, beneficiary, seller);
    }
}
