// SPDX-License-Identifier: GPL-3.0
pragma solidity 0.8.15;

import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {IERC721} from "@openzeppelin/contracts/token/ERC721/IERC721.sol";
import {IERC1155} from "@openzeppelin/contracts/token/ERC1155/IERC1155.sol";
import {SafeERC20} from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";

/// @title Asset Recoverer
/// @notice Recover ether, ERC20, ERC721 and ERC1155 from a derived contract
abstract contract AssetRecoverer {
    using SafeERC20 for IERC20;

    event EtherRecovered(address indexed recipient, uint256 amount);
    event ERC20Recovered(address indexed token, address indexed recipient, uint256 amount);
    event ERC721Recovered(address indexed token, uint256 tokenId, address indexed recipient);
    event ERC1155Recovered(address indexed token, uint256 tokenId, address indexed recipient, uint256 amount);

    /// @notice prevents burn for recovery functions
    /// @dev checks for zero address and reverts if true
    /// @param recipient address of the recovery recipient
    modifier burnDisallowed(address recipient) {
        require(recipient != address(0), "Recipient cannot be zero address!");
        _;
    }

    /// @notice recover all of ether on this contract as the owner
    /// @dev using the safer `call` instead of `transfer`
    /// @param recipient address to send ether to
    /// @param amount amount of ether to transfer
    function _recoverEther(address recipient, uint amount) internal virtual burnDisallowed(recipient) {
        (bool success, ) = recipient.call{value: amount}("");
        require(success);
        emit EtherRecovered(recipient, amount);
    }

    /// @notice recover an ERC20 token on this contract's balance as the owner
    /// @dev SafeERC20.safeTransfer doesn't return a bool as it performs an internal `require` check
    /// @param token address of the ERC20 token that is being recovered
    /// @param recipient address to transfer the tokens to
    /// @param amount amount of tokens to transfer
    function _recoverERC20(
        address token,
        address recipient,
        uint256 amount
    ) internal virtual burnDisallowed(recipient) {
        IERC20(token).safeTransfer(recipient, amount);
        emit ERC20Recovered(token, recipient, amount);
    }

    /// @notice recover an ERC721 token on this contract's balance as the owner
    /// @dev IERC721.safeTransferFrom doesn't return a bool as it performs an internal `require` check
    /// @param token address of the ERC721 token that is being recovered
    /// @param tokenId id of the individual token to transfer
    /// @param recipient address to transfer the token to
    function _recoverERC721(
        address token,
        uint256 tokenId,
        address recipient
    ) internal virtual burnDisallowed(recipient) {
        IERC721(token).safeTransferFrom(address(this), recipient, tokenId);
        emit ERC721Recovered(token, tokenId, recipient);
    }

    /// @notice recover an ERC1155 token on this contract's balance as the owner
    /// @dev IERC1155.safeTransferFrom doesn't return a bool as it performs an internal `require` check
    /// @param token address of the ERC1155 token that is being recovered
    /// @param tokenId id of the individual token to transfer
    /// @param recipient address to transfer the token to
    /// @param amount amount of tokens to transfer
    function _recoverERC1155(
        address token,
        uint256 tokenId,
        address recipient,
        uint256 amount
    ) internal virtual burnDisallowed(recipient) {
        IERC1155(token).safeTransferFrom(address(this), recipient, tokenId, amount, "");
        emit ERC1155Recovered(token, tokenId, recipient, amount);
    }
}
