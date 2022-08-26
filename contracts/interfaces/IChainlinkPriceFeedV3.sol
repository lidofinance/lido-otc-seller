// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

/// @title Minified Chainlink AggregatorV3Interface
interface IChainlinkPriceFeedV3 {
    function decimals() external view returns (uint8);

    function latestRoundData()
        external
        view
        returns (
            uint80 roundId,
            int256 answer,
            uint256 startedAt,
            uint256 updatedAt,
            uint80 answeredInRound
        );
}
