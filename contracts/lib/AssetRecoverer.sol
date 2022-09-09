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

    event EtherRecovered(address indexed _recipient, uint256 _amount);
    event ERC20Recovered(address indexed _token, address indexed _recipient, uint256 _amount);
    event ERC721Recovered(address indexed _token, uint256 _tokenId, address indexed _recipient);
    event ERC1155Recovered(address indexed _token, uint256 _tokenId, address indexed _recipient, uint256 _amount);

    /// @notice prevents burn for recovery functions
    /// @dev checks for zero address and reverts if true
    /// @param _recipient address of the recovery recipient
    modifier burnDisallowed(address _recipient) {
        require(_recipient != address(0), "Recipient cannot be zero address!");
        _;
    }

    /// @notice recover all of ether on this contract as the owner
    /// @dev using the safer `call` instead of `transfer`
    /// @param _recipient address to send ether to
    /// @param _amount amount of ether to transfer
    function _recoverEther(address _recipient, uint _amount) internal virtual burnDisallowed(_recipient) {
        (bool success, ) = _recipient.call{value: _amount}("");
        require(success);
        emit EtherRecovered(_recipient, _amount);
    }

    /// @notice recover an ERC20 token on this contract's balance as the owner
    /// @dev SafeERC20.safeTransfer doesn't return a bool as it performs an internal `require` check
    /// @param _token address of the ERC20 token that is being recovered
    /// @param _recipient address to transfer the tokens to
    /// @param _amount amount of tokens to transfer
    function _recoverERC20(
        address _token,
        address _recipient,
        uint256 _amount
    ) internal virtual burnDisallowed(_recipient) {
        IERC20(_token).safeTransfer(_recipient, _amount);
        emit ERC20Recovered(_token, _recipient, _amount);
    }

    /// @notice recover an ERC721 token on this contract's balance as the owner
    /// @dev IERC721.safeTransferFrom doesn't return a bool as it performs an internal `require` check
    /// @param _token address of the ERC721 token that is being recovered
    /// @param _tokenId id of the individual token to transfer
    /// @param _recipient address to transfer the token to
    function _recoverERC721(
        address _token,
        uint256 _tokenId,
        address _recipient
    ) internal virtual burnDisallowed(_recipient) {
        IERC721(_token).safeTransferFrom(address(this), _recipient, _tokenId);
        emit ERC721Recovered(_token, _tokenId, _recipient);
    }

    /// @notice recover an ERC1155 token on this contract's balance as the owner
    /// @dev IERC1155.safeTransferFrom doesn't return a bool as it performs an internal `require` check
    /// @param _token address of the ERC1155 token that is being recovered
    /// @param _tokenId id of the individual token to transfer
    /// @param _recipient address to transfer the token to
    /// @param _amount amount of tokens to transfer
    function _recoverERC1155(
        address _token,
        uint256 _tokenId,
        address _recipient,
        uint256 _amount
    ) internal virtual burnDisallowed(_recipient) {
        IERC1155(_token).safeTransferFrom(address(this), _recipient, _tokenId, _amount, "");
        emit ERC1155Recovered(_token, _tokenId, _recipient, _amount);
    }
}
