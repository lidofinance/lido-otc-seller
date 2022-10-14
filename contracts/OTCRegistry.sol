// SPDX-FileCopyrightText: 2022 Lido <info@lido.fi>
// SPDX-License-Identifier: MIT
pragma solidity 0.8.10;

import {Ownable} from "@openzeppelin/contracts/access/Ownable.sol";
import {Clones} from "@openzeppelin/contracts/proxy/Clones.sol";
import {EnumerableSet} from "@openzeppelin/contracts/utils/structs/EnumerableSet.sol";

import {OTCSeller} from "./OTCSeller.sol";
import {IOTCRegistry} from "./interfaces/IOTCRegistry.sol";
import {IChainlinkPriceFeedV3} from "./interfaces/IChainlinkPriceFeedV3.sol";

contract OTCRegistry is Ownable, IOTCRegistry {
    using EnumerableSet for EnumerableSet.AddressSet;

    event SellerCreated(address indexed token0, address indexed token1, address pair);
    event PairConfigSet(address indexed token0, address indexed token1, PairConfig config);

    address public immutable implementation;

    struct PairConfig {
        address priceFeed;
        // The maximum allowable spot price margin that can be set, in BPS
        uint16 maxMargin; // e.g. 200 = 2%
        bool reverse;
        uint256 constantPrice;
    }
    EnumerableSet.AddressSet private _sellers;

    mapping(address => mapping(address => PairConfig)) private _pairConfigs;

    constructor(
        address wethAddress,
        address daoVaultAddress,
        address beneficiaryAddress
    ) {
        implementation = address(new OTCSeller(wethAddress, daoVaultAddress, beneficiaryAddress));
    }

    /**
     * @notice forbids owner from renouncing ownership and locking assets forever
     * @dev overrides Ownable's `renounceOwnership` to always revert
     */
    function renounceOwnership() public pure override {
        revert("DISABLED");
    }

    function isSellerExists(address seller) external view returns (bool) {
        return _sellers.contains(seller);
    }

    function getSellersCount() external view returns (uint256) {
        return _sellers.length();
    }

    function getSellerByIndex(uint256 index) external view returns (address) {
        return _sellers.at(index);
    }

    function getAllSellers() external view returns (address[] memory) {
        return _sellers.values();
    }

    function getPairConfig(address tokenA, address tokenB) external view returns (PairConfig memory) {
        (address token0, address token1) = _sortTokens(tokenA, tokenB);
        return _pairConfigs[token0][token1];
    }

    function setPairConfig(
        address tokenA,
        address tokenB,
        address priceFeed,
        uint16 maxMargin,
        uint256 constantPrice
    ) external onlyOwner {
        _setPairConfig(tokenA, tokenB, priceFeed, maxMargin, constantPrice);
    }

    /// @dev calculates the Clone address for a pair
    function getSellerFor(address tokenA, address tokenB) external view returns (address seller) {
        (address token0, address token1) = _sortTokens(tokenA, tokenB);
        bytes32 salt = keccak256(abi.encodePacked(token0, token1));
        seller = Clones.predictDeterministicAddress(implementation, salt, address(this));
        // require(_sellers.contains(seller), "seller not exists");
    }

    /// @dev create the Clone for implementation and initialize it
    function createSeller(
        address tokenA,
        address tokenB,
        address priceFeed,
        uint16 maxMargin,
        uint256 constantPrice
    ) external onlyOwner returns (address seller) {
        (address token0, address token1) = _sortTokens(tokenA, tokenB);
        bytes32 salt = keccak256(abi.encodePacked(token0, token1));
        seller = Clones.predictDeterministicAddress(implementation, salt, address(this));
        require(_sellers.add(seller), "Seller exists"); // add seller addres to list

        _setPairConfig(tokenA, tokenB, priceFeed, maxMargin, constantPrice);

        require(seller == Clones.cloneDeterministic(implementation, salt), "Wrong clone address");
        OTCSeller(payable(seller)).initialize(tokenA, tokenB);
        emit SellerCreated(token0, token1, seller);
    }

    function getPriceAndMaxMargin(address tokenA, address tokenB) external view returns (uint256 price, uint16 maxMargin) {
        (address token0, address token1) = _sortTokens(tokenA, tokenB);
        PairConfig memory config = _pairConfigs[token0][token1];
        require(config.priceFeed != address(0) || config.constantPrice != 0, "Pair config not set");

        // if the requested tokens order is opposite to sorted order and in the same time
        // the priceFeed is also match the reverse sorted order, return direct (not reverse) price
        bool reverse = (token0 != tokenA) != config.reverse;

        // constantPrice has priority
        if (config.constantPrice > 0) {
            return (reverse ? 10**36 / config.constantPrice : config.constantPrice, config.maxMargin);
        }

        // return Chainlink price
        return (_getChainlinkPrice(config.priceFeed, reverse), config.maxMargin);
    }

    /// @dev Returns the normalized price from Chainlink price feed
    function _getChainlinkPrice(address priceFeed, bool reverse) internal view returns (uint256) {
        IChainlinkPriceFeedV3 _priceFeed = IChainlinkPriceFeedV3(priceFeed);
        uint256 decimals = _priceFeed.decimals();
        (, int256 price, , uint256 updatedAt, ) = _priceFeed.latestRoundData();
        require(updatedAt != 0, "Unexpected price feed answer");
        // normilize chainlink price to 18 decimals
        return reverse ? (10**(18 + decimals)) / uint256(price) : uint256(price) * (10**(18 - decimals));
    }

    function _sortTokens(address tokenA, address tokenB) internal pure returns (address token0, address token1) {
        require(tokenA != tokenB, "Identical addresses");
        (token0, token1) = tokenA < tokenB ? (tokenA, tokenB) : (tokenB, tokenA);
        require(token0 != address(0), "Zero address");
    }

    function _setPairConfig(
        address tokenA,
        address tokenB,
        address priceFeed,
        uint16 maxMargin,
        uint256 constantPrice
    ) internal {
        require(priceFeed != address(0) || constantPrice > 0, "either priceFeed or constantPrice is required");
        require(maxMargin > 0 && maxMargin <= 500, "maxMargin too high or not set");
        (address token0, address token1) = _sortTokens(tokenA, tokenB);

        bool reverse = token0 != tokenA;
        PairConfig memory config = PairConfig(priceFeed, maxMargin, reverse, constantPrice);

        _pairConfigs[token0][token1] = config;
        emit PairConfigSet(token0, token1, config);
    }
}
