// SPDX-License-Identifier: MIT
pragma solidity 0.8.15;

import {Initializable} from "@openzeppelin/contracts/proxy/utils/Initializable.sol";
import {AccessControlEnumerable} from "@openzeppelin/contracts/access/AccessControlEnumerable.sol";
import {ReentrancyGuard} from "@openzeppelin/contracts/security/ReentrancyGuard.sol";
/// @notice IERC20Metadata is used to support .decimals() method
import {IERC20Metadata as IERC20} from "@openzeppelin/contracts/token/ERC20/extensions/IERC20Metadata.sol";
import {SafeERC20} from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import {StorageSlot} from "@openzeppelin/contracts/utils/StorageSlot.sol";
import {ERC1967Implementation} from "./proxy/ERC1967Implementation.sol";
import {GPv2Order} from "./lib/GPv2Order.sol";
import {IUniswapRouterV2} from "./interfaces/IUniswapRouterV2.sol";
import {ICurveSmartRouter} from "./interfaces/ICurveSmartRouter.sol";
import {ICurveSynthSwap} from "./interfaces/ICurveSynthSwap.sol";
import {IChainlinkPriceFeedV3} from "./interfaces/IChainlinkPriceFeedV3.sol";
import {IGPv2Settlement} from "./interfaces/IGPv2Settlement.sol";
import {IWETH} from "./interfaces/IWETH.sol";

contract TokenSeller is Initializable, ERC1967Implementation, AccessControlEnumerable, ReentrancyGuard {
    using SafeERC20 for IERC20;
    using GPv2Order for GPv2Order.Data;
    using GPv2Order for bytes;

    bytes32 public constant ORDER_SETTLE_ROLE = keccak256("ORDER_SETTLE_ROLE");
    bytes32 public constant OPERATOR_ROLE = keccak256("OPERATOR_ROLE");

    uint32 public constant MIN_ORDER_VALID_TIME = 86400; // 24h

    uint256 private constant MAX_BPS = 10_000;
    // The maximum allowable slippage that can be set
    uint256 private constant MAX_SLIPPAGE = 500; // 5%

    // Stores current allowed slippage value, value is set in BPS
    bytes32 private constant _SLIPPAGE_SLOT = keccak256("lido.TokenSeller.slippage");

    address payable public constant LIDO_AGENT = payable(0x3e40D73EB977Dc6a537aF587D48316feE66E9C8c);

    /// Contract we give allowance to perform swaps
    address public constant GP_V2_VAULT_RELAYER = 0xC92E8bdf79f0507f65a392b0ab4667716BFE0110;
    address public constant GP_V2_SETTLEMENT = 0x9008D19f58AAbD9eD0D60971565AA8510560ab41;

    /// Token addressess
    address public constant TOKEN_ETH = 0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE;
    IERC20 public constant TOKEN_WETH = IERC20(0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2);
    IERC20 public constant TOKEN_DAI = IERC20(0x6B175474E89094C44Da98b954EedeAC495271d0F);
    IERC20 public constant TOKEN_USDC = IERC20(0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48);
    IERC20 public constant TOKEN_USDT = IERC20(0xdAC17F958D2ee523a2206206994597C13D831ec7);
    IERC20 public constant TOKEN_LDO = IERC20(0x5A98FcBEA516Cf06857215779Fd812CA3beF1B32);
    IERC20 public constant TOKEN_STETH = IERC20(0xae7ab96520DE3A18E5e111B5EaAb095312D7fE84);

    // Curve quote and swaps
    address public constant CURVE_SMART_ROUTER = 0xfA9a30350048B2BF66865ee20363067c66f67e58;
    address public constant CURVE_SYNTH_SWAP = 0x58A3c68e2D3aAf316239c003779F71aCb870Ee47;

    // Chainlink price feeds
    address public constant CHAINLINK_DAI_ETH = 0x773616E4d11A78F511299002da57A0a94577F1f4;
    address public constant CHAINLINK_USDT_ETH = 0xEe9F2375b4bdF6387aa8265dD4FB8F16512A1d46;
    address public constant CHAINLINK_USDC_ETH = 0x986b5E1e1755e3C2440e960477f25201B0a8bbD4;
    address public constant CHAINLINK_LDO_ETH = 0x4e844125952D32AcdF339BE976c98E22F6F318dB;
    address public constant CHAINLINK_STETH_ETH = 0x86392dC19c0b719886221c78AB11eb8Cf5c52812;

    /// @dev The EIP-712 domain separator
    /// @notice Copy pasted from Ethereum mainnet CowSwap settlement contract
    ///         See https://github.com/cowprotocol/contracts/blob/main/src/contracts/mixins/GPv2Signing.sol
    bytes32 public immutable domainSeparator = 0xc078f884a2676e1345748b1feace7b0abee5d00ecadb6e574dcdd109a63e8943;

    function initialize(uint256 slippage) external initializer onlyProxy {
        _setupRole(DEFAULT_ADMIN_ROLE, _msgSender());

        // assing roles for Lido Agent
        _setupRole(DEFAULT_ADMIN_ROLE, LIDO_AGENT);
        _setupRole(ORDER_SETTLE_ROLE, LIDO_AGENT);
        _setupRole(OPERATOR_ROLE, LIDO_AGENT);

        _setSlippage(slippage);
    }

    function getSlippage() external view returns (uint256) {
        return StorageSlot.getUint256Slot(_SLIPPAGE_SLOT).value;
    }

    /// @dev Set new slippage value
    function setSlippage(uint256 newSlippage) external {
        _checkRole(OPERATOR_ROLE);
        _setSlippage(newSlippage);
    }

    function _setSlippage(uint256 newSlippage) internal {
        require(newSlippage < MAX_SLIPPAGE, "TokenSeller: MAX_SLIPPAGE exceeded");
        StorageSlot.getUint256Slot(_SLIPPAGE_SLOT).value = newSlippage;
    }

    /// @dev Main entrypoint: Swap ETH -> DAI
    /// @notice Must be called only from address with SIGN_ROLE assigned, i.e. Lido Agent
    function swapETHForDAI(GPv2Order.Data calldata orderData, bytes memory orderUid) external payable {
        require(checkOrderETHForDAI(orderData, orderUid), "TokenSeller: order check failed");
        require(address(this).balance >= orderData.sellAmount, "TokenSeller: not enough ETH balance");

        // convert ETH to WETH
        IWETH(address(TOKEN_WETH)).deposit{value: orderData.sellAmount}();

        /// NOTE: _settleOrder also checks for msg.sender has SIGN_ROLE
        _settleOrder(orderData, orderUid);
    }

    function checkOrderETHForDAI(GPv2Order.Data calldata orderData, bytes memory orderUid) public view returns (bool) {
        require(orderData.sellToken == TOKEN_WETH, "TokenSeller: wrong WETH token");
        require(orderData.buyToken == TOKEN_DAI, "TokenSeller: wrong DAI token");

        // get Chainlink DAI/ETH price
        uint256 chainlinkPrice = getChainlinkDirectPrice(CHAINLINK_DAI_ETH);
        return checkOrder(orderData, orderUid, chainlinkPrice);
    }

    function getOrderUid(GPv2Order.Data calldata orderData) public view returns (bytes memory) {
        // Allocated
        bytes memory orderUid = new bytes(GPv2Order.UID_LENGTH);
        // Get the hash
        bytes32 digest = GPv2Order.hash(orderData, domainSeparator);
        GPv2Order.packOrderUidParams(orderUid, digest, address(this), orderData.validTo);
        return orderUid;
    }

    function checkOrder(
        GPv2Order.Data calldata orderData,
        bytes memory orderUid,
        uint256 chainlinkPrice
    ) public view returns (bool) {
        // Verify we get the same ID
        // NOTE: technically superfluous as we could just derive the id and setPresignature with that
        // But nice for internal testing
        bytes memory derivedOrderID = getOrderUid(orderData);
        require(keccak256(derivedOrderID) == keccak256(orderUid), "TokenSeller: orderUid missmatch");

        require(orderData.validTo > block.timestamp + MIN_ORDER_VALID_TIME, "TokenSeller: order validity time is too short");
        require(orderData.receiver == address(this), "TokenSeller: wrong order receiver");
        require(orderData.kind == GPv2Order.KIND_SELL, "TokenSeller: wrong order kind");
        require(orderData.sellTokenBalance == GPv2Order.BALANCE_ERC20, "TokenSeller: wrong order sellTokenBalance");
        require(orderData.buyTokenBalance == GPv2Order.BALANCE_ERC20, "TokenSeller: wrong order buyTokenBalance");

        // TODO: This should be done by using a gas cost oracle (see Chainlink)
        require(orderData.feeAmount <= orderData.sellAmount / 10, "TokenSeller: order fee to high"); // Fee can be at most 1/10th of order

        // Check the price we're agreeing to
        uint256 slippage = StorageSlot.getUint256Slot(_SLIPPAGE_SLOT).value;

        uint8 tokenSellDecimals = orderData.sellToken.decimals();
        uint8 tokenBuyDecimals = orderData.buyToken.decimals();

        // Get quote for "1" equivalent of orderData.sellToken
        uint256 bestPrice = getBestSwapPrice(address(orderData.sellToken), address(orderData.buyToken), 10**tokenSellDecimals);

        uint256 swapAmountOut = (orderData.sellAmount * bestPrice * (MAX_BPS - slippage)) / MAX_BPS / 10**tokenSellDecimals;
        // chainlinkPrice is normilized to 1e18 decimals, so we need to adjust it
        uint256 chainlinkAmountOut = (orderData.sellAmount * chainlinkPrice * (MAX_BPS - slippage)) /
            MAX_BPS /
            10**(18 + tokenSellDecimals - tokenBuyDecimals);

        // Require that Cowswap is offering a better price or matching
        return (swapAmountOut <= orderData.buyAmount && chainlinkAmountOut <= orderData.buyAmount);
    }

    /// @dev View function for testing the routing of the strategy
    function getBestSwapPrice(
        address tokenIn,
        address tokenOut,
        uint256 amountIn
    ) public view returns (uint256 bestPrice) {
        uint256 length = 2; // set length as need
        uint256[] memory prices = new uint256[](length);

        // Additional providers can be added later
        uint256 curveQuote = getCurvePrice(tokenIn, tokenOut, amountIn);
        prices[0] = curveQuote;

        uint256 curveSynthQuote = getCurveSynthPrice(tokenIn, tokenOut, amountIn);
        prices[1] = curveSynthQuote;

        // O(n) complexity and each check is like 9 gas
        bestPrice = prices[0];
        unchecked {
            for (uint256 x = 1; x < length; ++x) {
                if (prices[x] > bestPrice) {
                    bestPrice = prices[x];
                }
            }
        }
    }

    /// @dev Get quote from the Curve Smart Router, the input amount, and the path, returns the quote for it
    function getCurvePrice(
        address tokenIn,
        address tokenOut,
        uint256 amountIn
    ) public view returns (uint256) {
        uint256 quote; // = 0
        // fix ETH token address to get correct route
        if (tokenIn == address(TOKEN_WETH)) {
            tokenIn = address(TOKEN_ETH);
        } else if (tokenOut == address(TOKEN_WETH)) {
            tokenOut = address(TOKEN_ETH);
        }

        try ICurveSmartRouter(CURVE_SMART_ROUTER).get_exchange_routing(tokenIn, tokenOut, amountIn) returns (
            address[6] memory,
            uint256[8] memory,
            uint256 curveQuote
        ) {
            quote = curveQuote;
        } catch (bytes memory) {
            // We ignore as it means it's zero
        }
        return quote;
    }

    /// @dev  Get quote from the Curve Synth, the input amount, and the path, returns the quote for it
    function getCurveSynthPrice(
        address tokenIn,
        address tokenOut,
        uint256 amountIn
    ) public view returns (uint256) {
        uint256 quote; // = 0
        // fix ETH token address to get correct route
        if (tokenIn == address(TOKEN_WETH)) {
            tokenIn = address(TOKEN_ETH);
        } else if (tokenOut == address(TOKEN_WETH)) {
            tokenOut = address(TOKEN_ETH);
        }

        try ICurveSynthSwap(CURVE_SYNTH_SWAP).get_estimated_swap_amount(tokenIn, tokenOut, amountIn) returns (uint256 curveQuote) {
            quote = curveQuote;
        } catch (bytes memory) {
            // We ignore as it means it's zero
        }
        return quote;
    }

    /// @dev Returns the normalized price from Chainlink price feed
    function getChainlinkDirectPrice(address priceFeed) public view returns (uint256) {
        uint256 decimals = IChainlinkPriceFeedV3(priceFeed).decimals();
        (, int256 price, , uint256 updated_at, ) = IChainlinkPriceFeedV3(priceFeed).latestRoundData();
        require(updated_at != 0, "TokenSeller: unexpected price feed answer");
        return uint256(price) * (10**(18 - decimals));
    }

    /// @dev Returns the reversed normalized price from Chainlink price feed, i.e. 1/price
    function getChainlinkReversePrice(address priceFeed) public view returns (uint256) {
        return 10**36 / getChainlinkDirectPrice(priceFeed);
    }

    /// @dev This is the function you want to use to perform a swap on Cowswap via this smart contract
    function _settleOrder(GPv2Order.Data calldata orderData, bytes memory orderUid) internal nonReentrant {
        _checkRole(ORDER_SETTLE_ROLE);

        // Because swap is looking good, check we have the amount, then give allowance to the Cowswap Router
        orderData.sellToken.safeApprove(GP_V2_VAULT_RELAYER, 0); // Set to 0 just in case
        orderData.sellToken.safeApprove(GP_V2_VAULT_RELAYER, orderData.sellAmount);

        // Once allowance is set, let's setPresignature and the order will happen
        //setPreSignature
        IGPv2Settlement(GP_V2_SETTLEMENT).setPreSignature(orderUid, true);
    }

    /// @dev Allows to cancel a cowswap order perhaps if it took too long or was with invalid parameters
    /// @notice This function performs no checks, there's a high change it will revert if you send it with fluff parameters
    function _cancelOrder(bytes memory orderUid) internal nonReentrant {
        _checkRole(OPERATOR_ROLE);
        IGPv2Settlement(GP_V2_SETTLEMENT).setPreSignature(orderUid, false);
    }
}
