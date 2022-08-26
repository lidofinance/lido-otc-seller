// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

/// @title Minified CowSwap GPv2Settlement interface
interface IGPv2Settlement {
    /// @dev Sets a presignature for the specified order UID.
    ///
    /// @param orderUid The unique identifier of the order to pre-sign.
    function setPreSignature(bytes calldata orderUid, bool signed) external;

    function preSignature(bytes calldata orderUid) external view returns (uint256);

    function domainSeparator() external view returns (bytes32);
}
