// SPDX-License-Identifier: MIT
pragma solidity 0.8.15;

import {Initializable} from "@openzeppelin/contracts/proxy/utils/Initializable.sol";
/// @notice IERC20Metadata is used to support .decimals() method
import {IERC20Metadata as IERC20} from "@openzeppelin/contracts/token/ERC20/extensions/IERC20Metadata.sol";
import {SafeERC20} from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";

import {GPv2Order} from "./lib/GPv2Order.sol";
import {AssetRecoverer} from "./lib/AssetRecoverer.sol";

import {IGPv2Settlement} from "./interfaces/IGPv2Settlement.sol";
import {IWETH} from "./interfaces/IWETH.sol";
import {IVault} from "./interfaces/IVault.sol";
import {IOTCRegistry} from "./interfaces/IOTCRegistry.sol";

contract OTCSeller is Initializable, AssetRecoverer {
    using SafeERC20 for IERC20;
    using GPv2Order for GPv2Order.Data;
    using GPv2Order for bytes;

    uint16 private constant MAX_BPS = 10_000;

    /// Contract we give allowance to perform swaps
    /// The addresses are the same in all chains, so we can hardcode it
    address public constant GP_V2_VAULT_RELAYER = 0xC92E8bdf79f0507f65a392b0ab4667716BFE0110;
    address public constant GP_V2_SETTLEMENT = 0x9008D19f58AAbD9eD0D60971565AA8510560ab41;

    // events
    event OrderSettled(address indexed caller, bytes orderUid, address sellToken, address buyToken, uint256 sellAmount, uint256 buyAmount);
    event OrderCanceled(address indexed caller, bytes orderUid);

    /// WETH or analog address
    address public immutable WETH;
    /// Lido Agent (Vault) address
    address public immutable DAO_VAULT;
    address public immutable BENEFICIARY;
    address public immutable registry;

    struct Pair {
        address sellToken;
        address buyToken;
    }
    Pair private _pair;

    constructor(
        address wethAddress,
        address daoVaultAddress,
        address beneficiaryAddress
    ) {
        require(wethAddress != address(0) && daoVaultAddress != address(0) && beneficiaryAddress != address(0), "Zero address");
        WETH = wethAddress;
        DAO_VAULT = daoVaultAddress;
        BENEFICIARY = beneficiaryAddress;
        registry = msg.sender;
    }

    modifier onlyRegistry() {
        require(msg.sender == registry, "Only registry can call");
        _;
    }

    /// @notice sellToken and buyToken mast be set in order according chainlink price feed
    ///         i.e., in the case of selling ETH for DAI, the sellToken must be set to DAI,
    ///         as the chainlink price feed returns the ETH amount for 1DAI
    function initialize(address _sellToken, address _buyToken) external initializer onlyRegistry {
        /// @notice contract works only with ERC20 compatile tokens
        require(_sellToken != address(0) && _buyToken != address(0), "Zero address");
        require(_sellToken != _buyToken, "sellToken and buyToken must be different");

        _pair = Pair(_sellToken, _buyToken);
    }

    /// @dev allow contract to receive ETH
    /// @notice all received ETH are converted to WETH due to CowSwap only works with WETH
    receive() external payable {
        // wrap all income ETH to WETH
        IWETH(WETH).deposit{value: msg.value}();
    }

    fallback() external {
        revert();
    }

    function deposit(address token, uint256 amount) external {
        IERC20(token).safeTransferFrom(msg.sender, address(this), amount);
    }

    function tokensPair() external view returns (address, address) {
        return (_pair.sellToken, _pair.buyToken);
    }

    function priceAndMaxSlippage() external view returns (uint256 price, uint16 slippage) {
        return _getPriceAndMaxSlippage(_pair.sellToken, _pair.buyToken);
    }

    /// @dev Calculates OrderUid from Order Data
    function getOrderUid(GPv2Order.Data calldata orderData) public view returns (bytes memory) {
        // Allocated
        bytes memory orderUid = new bytes(GPv2Order.UID_LENGTH);
        // Get the hash
        bytes32 digest = GPv2Order.hash(orderData, IGPv2Settlement(GP_V2_SETTLEMENT).domainSeparator());
        GPv2Order.packOrderUidParams(orderUid, digest, address(this), orderData.validTo);
        return orderUid;
    }

    /// @dev General order data checks.
    /// @notice receiver is the seller contract itself, since the Vault Agent
    ///         cannot detect the direct transfer of the token, so it is necessary to complete
    ///         the execution of the sale on the Seller contract and transfer the tokens
    ///         through the .deposit () method
    function checkOrder(GPv2Order.Data calldata orderData, bytes calldata orderUid) public view returns (bool) {
        _checkTokensPair(address(orderData.sellToken), address(orderData.buyToken));
        require(orderData.validTo > block.timestamp, "validTo in the past");
        // NOTE: receiver is the seller contract itself, since the Vault Agent cannot detect the direct transfer of the token, so it is necessary to complete the execution of the sale on the Seller contract and transfer the tokens through the .deposit () method
        require(orderData.receiver == BENEFICIARY, "Wrong receiver");
        require(orderData.partiallyFillable == false, "Partially fill not allowed");
        require(orderData.kind == GPv2Order.KIND_SELL, "Wrong order kind");
        require(orderData.sellTokenBalance == GPv2Order.BALANCE_ERC20, "Wrong order sellTokenBalance");
        require(orderData.buyTokenBalance == GPv2Order.BALANCE_ERC20, "Wrong order buyTokenBalance");

        // Verify we get the same ID
        bytes memory derivedOrderID = getOrderUid(orderData);
        require(keccak256(derivedOrderID) == keccak256(orderUid), "orderUid missmatch");

        require(orderData.feeAmount <= orderData.sellAmount / 10, "Order fee to high"); // Fee can be at most 1/10th of order

        // Check the price we're agreeing to and max slippage
        (uint256 price, uint16 slippage) = _getPriceAndMaxSlippage(address(orderData.sellToken), address(orderData.buyToken));
        uint8 tokenSellDecimals = orderData.sellToken.decimals();
        uint8 tokenBuyDecimals = orderData.buyToken.decimals();

        // chainlinkPrice is normilized to 1e18 decimals, so we need to adjust it
        uint256 swapAmountOut = (orderData.sellAmount * price * (MAX_BPS - slippage)) / MAX_BPS / 10**(18 + tokenSellDecimals - tokenBuyDecimals);

        // Require that Cowswap is offering a better price or matching
        return (swapAmountOut <= orderData.buyAmount);
    }

    /// @dev Function to perform a swap on Cowswap via this smart contract
    /// @notice Can be called by anyone
    function settleOrder(GPv2Order.Data calldata orderData, bytes calldata orderUid) external payable {
        require(checkOrder(orderData, orderUid), "buyAmount too low");

        orderData.sellToken.safeIncreaseAllowance(GP_V2_VAULT_RELAYER, orderData.sellAmount);
        // setPresignature to order will happen
        IGPv2Settlement(GP_V2_SETTLEMENT).setPreSignature(orderUid, true);

        emit OrderSettled(msg.sender, orderUid, address(orderData.sellToken), address(orderData.buyToken), orderData.sellAmount, orderData.buyAmount);
    }

    /// @dev Cancel settled but not yet filled order
    /// @notice Can be called only by beneficiary
    function cancelOrder(bytes calldata orderUid) external {
        _checkBeneficiary();

        uint256 soldAmount = IGPv2Settlement(GP_V2_SETTLEMENT).filledAmount(orderUid);
        require(soldAmount == 0, "Order already filled");

        // reset setPresignature
        IGPv2Settlement(GP_V2_SETTLEMENT).setPreSignature(orderUid, false);

        emit OrderCanceled(msg.sender, orderUid);
    }

    /// @notice Can be called by anyone except case when token is sellToken or buyToken
    function recoverERC20(address token, uint256 amount) external {
        if (token == _pair.sellToken || token == _pair.buyToken) {
            _checkBeneficiary();
        }
        _recoverERC20(token, BENEFICIARY, amount);
    }

    /// @notice Can be called by anyone
    function recoverEther(uint256 amount) external {
        _recoverEther(BENEFICIARY, amount);
    }

    /// @notice Can be called by anyone
    function recoverERC721(address token, uint256 tokenId) external {
        _recoverERC721(token, tokenId, BENEFICIARY);
    }

    /// @notice Can be called by anyone
    function recoverERC1155(
        address token,
        uint256 tokenId,
        uint256 amount
    ) external {
        _recoverERC1155(token, tokenId, BENEFICIARY, amount);
    }

    function _recoverERC20(
        address token,
        address recipient,
        uint256 amount
    ) internal virtual override {
        if (recipient == DAO_VAULT) {
            IERC20(token).safeIncreaseAllowance(DAO_VAULT, amount);
            IVault(DAO_VAULT).deposit(token, amount);
            emit ERC20Recovered(token, DAO_VAULT, amount);
        } else {
            super._recoverERC20(token, recipient, amount);
        }
    }

    function _checkBeneficiary() internal view {
        require(msg.sender == BENEFICIARY, "Only beneficiary has access");
    }

    function _checkTokensPair(address sellToken, address buyToken) internal view {
        address _sellTokenn = _pair.sellToken;
        address _buyToken = _pair.buyToken;
        require((sellToken == _sellTokenn && buyToken == _buyToken) || (sellToken == _buyToken && buyToken == _sellTokenn), "Unsuported tokens pair");
    }

    function _getPriceAndMaxSlippage(address tokenA, address tokenB) internal view returns (uint256 price, uint16 slippage) {
        (price, slippage) = IOTCRegistry(registry).getPriceAndMaxSlippage(tokenA, tokenB);
        require(price > 0, "price not defined");
        require(slippage > 0, "slippage not defined");
    }
}
