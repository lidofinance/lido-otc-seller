// SPDX-FileCopyrightText: 2022 Lido <info@lido.fi>
// SPDX-License-Identifier: MIT
pragma solidity 0.8.10;

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
    event OrderSigned(address indexed caller, bytes orderUid, address sellToken, address buyToken, uint256 sellAmount, uint256 buyAmount);
    event OrderCanceled(address indexed caller, bytes orderUid);

    /// WETH or analog address
    address public immutable WETH;
    /// Lido Agent (Vault) address
    address public immutable DAO_VAULT;
    address public immutable BENEFICIARY;
    address public immutable registry;

    address public tokenA;
    address public tokenB;

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
    function initialize(address _tokenA, address _tokenB) external initializer onlyRegistry {
        /// @notice contract works only with ERC20 compatible tokens
        require(_tokenA != address(0) && _tokenB != address(0), "Zero address");
        require(_tokenA != _tokenB, "tokenA and tokenB must be different");

        tokenA = _tokenA;
        tokenB = _tokenB;
    }

    /// @dev allow contract to receive ETH
    /// @notice all received ETH are converted to WETH due to CowSwap only works with WETH
    receive() external payable {
        require(tokenA == WETH || tokenB == WETH, "ETH not accepted");
        // wrap all income ETH to WETH
        IWETH(WETH).deposit{value: msg.value}();
    }

    fallback() external {
        revert();
    }

    function priceAndMaxMargin() external view returns (uint256 price, uint16 maxMargin) {
        return _getPriceAndMaxMargin(tokenA, tokenB);
    }

    function reversePriceAndMaxMargin() external view returns (uint256 price, uint16 maxMargin) {
        return _getPriceAndMaxMargin(tokenB, tokenA);
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

    /// @dev Get min acceptable amount to buy (according priceFeed and maxMargin)
    function minBuyAmount(
        IERC20 sellToken,
        IERC20 buyToken,
        uint256 sellAmount
    ) public view returns (uint256 buyAmount) {
        // Check the price we're agreeing to and max price margin
        (uint256 price, uint16 maxMargin) = _getPriceAndMaxMargin(address(sellToken), address(buyToken));
        uint8 tokenSellDecimals = sellToken.decimals();
        uint8 tokenBuyDecimals = buyToken.decimals();

        // chainlinkPrice is normalized to 1e18 decimals, so we need to adjust it
        buyAmount = ((sellAmount * price * (MAX_BPS - maxMargin)) / MAX_BPS) / (10**(18 + tokenSellDecimals - tokenBuyDecimals));
    }

    /// @dev General order data checks.
    /// @notice The receiver must be a "beneficiary" to avoid the purchased tokens appearing on the contract address
    function checkOrder(GPv2Order.Data calldata orderData, bytes calldata orderUid) public view returns (bool success, string memory result) {
        result = _checkTokensPair(address(orderData.sellToken), address(orderData.buyToken));
        if (bytes(result).length > 0) return (false, result);
        result = _checkOrderParams(orderData);
        if (bytes(result).length > 0) return (false, result);

        // Verify we get the same ID
        bytes memory derivedOrderID = getOrderUid(orderData);
        if (keccak256(derivedOrderID) != keccak256(orderUid)) {
            return (false, "orderUid mismatch");
        }

        if (orderData.feeAmount > orderData.sellAmount / 10) {
            // Fee can be at most 1/10th of order
            return (false, "Order fee to high");
        }

        uint256 minAcceptableBuyAmount = minBuyAmount(orderData.sellToken, orderData.buyToken, orderData.sellAmount);

        // Require that Cowswap is offering a better price or matching
        if (minAcceptableBuyAmount > orderData.buyAmount) {
            return (false, "buyAmount too low");
        }
        return (true, "");
    }

    /// @dev Function to perform a swap on Cowswap via this smart contract
    /// @notice Can be called by anyone
    function signOrder(GPv2Order.Data calldata orderData, bytes calldata orderUid) external payable {
        (bool checked, string memory result) = checkOrder(orderData, orderUid);
        require(checked, result);

        orderData.sellToken.safeIncreaseAllowance(GP_V2_VAULT_RELAYER, orderData.sellAmount);
        // setPresignature to order will happen
        IGPv2Settlement(GP_V2_SETTLEMENT).setPreSignature(orderUid, true);

        emit OrderSigned(msg.sender, orderUid, address(orderData.sellToken), address(orderData.buyToken), orderData.sellAmount, orderData.buyAmount);
    }

    /// @dev Cancel signed but not yet filled order
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
    function transferERC20(address token, uint256 amount) external {
        if (token == tokenA || token == tokenB) {
            _checkBeneficiary();
        }
        _transferERC20(token, BENEFICIARY, amount);
    }

    /// @notice Can be called by anyone
    function transferEther(uint256 amount) external {
        _transferEther(BENEFICIARY, amount);
    }

    /// @notice Can be called by anyone
    function transferERC721(
        address token,
        uint256 tokenId,
        bytes calldata data
    ) external {
        require(token != tokenA && token != tokenB, "Wrong token address");
        _transferERC721(token, BENEFICIARY, tokenId, data);
    }

    /// @notice Can be called by anyone
    function transferERC1155(
        address token,
        uint256 tokenId,
        uint256 amount,
        bytes calldata data
    ) external {
        require(token != tokenA && token != tokenB, "Wrong token address");
        _transferERC1155(token, BENEFICIARY, tokenId, amount, data);
    }

    function _transferERC20(
        address token,
        address recipient,
        uint256 amount
    ) internal virtual override {
        if (recipient == DAO_VAULT) {
            IERC20(token).safeIncreaseAllowance(recipient, amount);
            IVault(DAO_VAULT).deposit(token, amount);
            emit ERC20Transferred(token, recipient, amount);
        } else {
            super._transferERC20(token, recipient, amount);
        }
    }

    function _checkBeneficiary() internal view {
        require(msg.sender == BENEFICIARY, "Only beneficiary has access");
    }

    function _checkTokensPair(address sellToken, address buyToken) internal view returns (string memory resut) {
        address _sellToken = tokenA;
        address _buyToken = tokenB;
        if (!(sellToken == _sellToken && buyToken == _buyToken) && !(sellToken == _buyToken && buyToken == _sellToken)) return "Unsupported tokens pair";
    }

    function _checkOrderParams(GPv2Order.Data calldata orderData) internal view returns (string memory resut) {
        if (orderData.validTo <= block.timestamp) return "validTo in the past";
        if (orderData.receiver != BENEFICIARY) return "Wrong receiver";
        if (orderData.partiallyFillable == true) return "Partially fill not allowed";
        if (orderData.kind != GPv2Order.KIND_SELL) return "Wrong order kind";

        //Check the TokenBalance marker value for using direct ERC20 balances for computing the order struct hash.
        if (orderData.sellTokenBalance != GPv2Order.BALANCE_ERC20) return "Wrong order sellTokenBalance marker";
        if (orderData.buyTokenBalance != GPv2Order.BALANCE_ERC20) return "Wrong order buyTokenBalance marker";
    }

    function _getPriceAndMaxMargin(address sellToken, address buyToken) internal view returns (uint256 price, uint16 maxMargin) {
        (price, maxMargin) = IOTCRegistry(registry).getPriceAndMaxMargin(sellToken, buyToken);
        require(price > 0, "price not defined");
        require(maxMargin > 0, "maxMargin not defined");
    }
}
