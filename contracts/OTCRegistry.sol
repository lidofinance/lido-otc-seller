// SPDX-License-Identifier: MIT
pragma solidity 0.8.15;

import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/proxy/Clones.sol";
import "@openzeppelin/contracts/utils/structs/EnumerableSet.sol";

import "./OTCSeller.sol";

contract OTCRegistry is Ownable {
    using EnumerableSet for EnumerableSet.AddressSet;

    event SellerCreated(address indexed token0, address indexed token1, address pair);

    address public immutable implementation;

    EnumerableSet.AddressSet private _sellers;

    constructor(
        address wethAddress,
        address daoVaultAddress,
        address beneficiaryAddress
    ) {
        implementation = address(new OTCSeller(wethAddress, daoVaultAddress, beneficiaryAddress));
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

    /// @dev calculates the Clone address for a pair
    function getSellerFor(address tokenA, address tokenB) external view returns (address seller) {
        (address token0, address token1) = _sortTokens(tokenA, tokenB);
        bytes32 salt = keccak256(abi.encodePacked(token0, token1));
        seller = Clones.predictDeterministicAddress(implementation, salt, address(this));
        // require(_sellers.contains(seller), "seller not exists");
    }

    /// @dev create the Clone for implementation ant initialize it
    function createSeller(
        address tokenA,
        address tokenB,
        address priceFeed,
        uint16 maxSlippage
    ) external onlyOwner returns (address seller) {
        (address token0, address token1) = _sortTokens(tokenA, tokenB);
        bytes32 salt = keccak256(abi.encodePacked(token0, token1));
        seller = Clones.predictDeterministicAddress(implementation, salt, address(this));
        require(_sellers.add(seller), "Seller exists"); // add seller addres to list

        require(seller == Clones.cloneDeterministic(implementation, salt), "wrong clone address");
        OTCSeller(payable(seller)).initialize(tokenA, tokenB, priceFeed, maxSlippage);

        emit SellerCreated(token0, token1, seller);
    }

    function _sortTokens(address tokenA, address tokenB) internal pure returns (address token0, address token1) {
        require(tokenA != tokenB, "Identical addresses");
        (token0, token1) = tokenA < tokenB ? (tokenA, tokenB) : (tokenB, tokenA);
        require(token0 != address(0), "Zero address");
    }
}
