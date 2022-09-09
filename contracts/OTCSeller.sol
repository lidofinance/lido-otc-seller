// SPDX-License-Identifier: MIT
pragma solidity 0.8.15;

/// @notice IERC20Metadata is used to support .decimals() method
import {IERC20Metadata as IERC20} from "@openzeppelin/contracts/token/ERC20/extensions/IERC20Metadata.sol";
import {SafeERC20} from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";

import {GPv2Order} from "./lib/GPv2Order.sol";
import {AssetRecoverer} from "./lib/AssetRecoverer.sol";

import {IChainlinkPriceFeedV3} from "./interfaces/IChainlinkPriceFeedV3.sol";
import {IGPv2Settlement} from "./interfaces/IGPv2Settlement.sol";
import {IWETH} from "./interfaces/IWETH.sol";
import {IVault} from "./interfaces/IVault.sol";

contract OTCSeller is AssetRecoverer {
    using SafeERC20 for IERC20;
    using GPv2Order for GPv2Order.Data;
    using GPv2Order for bytes;

    uint256 private constant MAX_BPS = 10_000;
    address payable public constant LIDO_AGENT = payable(0x3e40D73EB977Dc6a537aF587D48316feE66E9C8c);

    /// Contract we give allowance to perform swaps
    address public constant GP_V2_VAULT_RELAYER = 0xC92E8bdf79f0507f65a392b0ab4667716BFE0110;
    address public constant GP_V2_SETTLEMENT = 0x9008D19f58AAbD9eD0D60971565AA8510560ab41;

    /// WETH
    IWETH public constant WETH = IWETH(0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2);

    // events
    event OrderSettled(address indexed caller, bytes orderUid, address sellToken, address buyToken, uint256 sellAmount, uint256 buyAmount);
    event OrderCanceled(address indexed caller, bytes orderUid);

    /// @dev The EIP-712 domain separator
    /// @notice Copy pasted from Ethereum mainnet CowSwap settlement contract
    ///         See https://github.com/cowprotocol/contracts/blob/main/src/contracts/mixins/GPv2Signing.sol
    bytes32 public immutable domainSeparator = 0xc078f884a2676e1345748b1feace7b0abee5d00ecadb6e574dcdd109a63e8943;

    IERC20 public immutable sellToken;
    IERC20 public immutable buyToken;
    IChainlinkPriceFeedV3 public immutable priceFeed;
    address public immutable beneficiary;
    // The maximum allowable slippage that can be set, in BPS
    uint256 public immutable maxSlippage; // e.g. 200 = 2%

    /// @notice sellToken and buyToken mast be set in order according chainlink price feed
    ///         i.e., in the case of selling ETH for DAI, the sellToken must be set to DAI,
    ///         as the chainlink price feed returns the ETH amount for 1DAI
    constructor(
        address _sellToken,
        address _buyToken,
        address _priceFeed,
        address _beneficiary,
        uint256 _maxSlippage
    ) {
        /// @notice contract works only with ERC20 compatile tokens
        require(_sellToken != address(0) && _buyToken != address(0), "sellToken or buyToken are required");
        require(_sellToken != _buyToken, "sellToken and buyToken must be different");
        require(_priceFeed != address(0), "priceFeed is required");
        require(_beneficiary != address(0), "receiver is required");
        require(_maxSlippage <= 500, "maxSlippage too high");

        sellToken = IERC20(_sellToken);
        buyToken = IERC20(_buyToken);
        priceFeed = IChainlinkPriceFeedV3(_priceFeed);
        beneficiary = _beneficiary;
        maxSlippage = _maxSlippage;
    }

    /// @dev allow contract to receive ETH
    /// @notice all received ETH are converted to WETH due to CowSwap only works with WETH
    receive() external payable {
        // wrap all income ETH to WETH
        WETH.deposit{value: msg.value}();
    }

    fallback() external {
        revert();
    }

    /// @dev Returns the normalized price from Chainlink price feed
    function getChainlinkDirectPrice() public view returns (uint256) {
        uint256 decimals = priceFeed.decimals();
        (, int256 price, , uint256 updated_at, ) = priceFeed.latestRoundData();
        require(updated_at != 0, "Unexpected price feed answer");
        // normilize chainlink price to 18 decimals
        return uint256(price) * (10**(18 - decimals));
    }

    /// @dev Returns the reversed normalized price from Chainlink price feed, i.e. 1/price
    function getChainlinkReversePrice() public view returns (uint256) {
        return 10**36 / getChainlinkDirectPrice();
    }

    /// @dev Calculates OrderUid from Order Data
    function getOrderUid(GPv2Order.Data calldata orderData) public view returns (bytes memory) {
        // Allocated
        bytes memory orderUid = new bytes(GPv2Order.UID_LENGTH);
        // Get the hash
        bytes32 digest = GPv2Order.hash(orderData, domainSeparator);
        GPv2Order.packOrderUidParams(orderUid, digest, address(this), orderData.validTo);
        return orderUid;
    }

   
    /// @dev General order data checks.
    /// @notice receiver is the seller contract itself, since the Vault Agent
    ///         cannot detect the direct transfer of the token, so it is necessary to complete
    ///         the execution of the sale on the Seller contract and transfer the tokens
    ///         through the .deposit () method
    function checkOrder(GPv2Order.Data calldata orderData, bytes calldata orderUid) public view returns (bool) {
        require(orderData.validTo > block.timestamp, "validTo in the past");
        // NOTE: receiver is the seller contract itself, since the Vault Agent cannot detect the direct transfer of the token, so it is necessary to complete the execution of the sale on the Seller contract and transfer the tokens through the .deposit () method
        require(orderData.receiver == beneficiary, "Wrong receiver");
        require(orderData.partiallyFillable == false, "Partially fill not allowed");
        require(orderData.kind == GPv2Order.KIND_SELL, "Wrong order kind");
        require(orderData.sellTokenBalance == GPv2Order.BALANCE_ERC20, "Wrong order sellTokenBalance");
        require(orderData.buyTokenBalance == GPv2Order.BALANCE_ERC20, "Wrong order buyTokenBalance");

        bool reverse = _checkTokensReverseOrder(orderData.sellToken, orderData.buyToken);
        // Verify we get the same ID
        bytes memory derivedOrderID = getOrderUid(orderData);
        require(keccak256(derivedOrderID) == keccak256(orderUid), "orderUid missmatch");

        // TODO: This should be done by using a gas cost oracle (see Chainlink)
        require(orderData.feeAmount <= orderData.sellAmount / 10, "Order fee to high"); // Fee can be at most 1/10th of order

        // Check the price we're agreeing to
        uint256 slippage = maxSlippage;

        // get Chainlink direct price
        uint256 chainlinkPrice = reverse ? getChainlinkReversePrice() : getChainlinkDirectPrice();
        uint8 tokenSellDecimals = orderData.sellToken.decimals();
        uint8 tokenBuyDecimals = orderData.buyToken.decimals();

        // chainlinkPrice is normilized to 1e18 decimals, so we need to adjust it
        uint256 swapAmountOut = (orderData.sellAmount * chainlinkPrice * (MAX_BPS - slippage)) / MAX_BPS / 10**(18 + tokenSellDecimals - tokenBuyDecimals);

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
    function recoverERC20(address _token, uint256 _amount) external {
        if (_token == address(sellToken) || _token == address(buyToken)) {
            _checkBeneficiary();
        }
        _recoverERC20(_token, beneficiary, _amount);
    }

    /// @notice Can be called by anyone
    function recoverEther(uint256 _amount) external {
        _recoverEther(beneficiary, _amount);
    }

    /// @notice Can be called by anyone
    function recoverERC721(address _token, uint256 _tokenId) external {
        _recoverERC721(_token, _tokenId, beneficiary);
    }

    /// @notice Can be called by anyone
    function recoverERC1155(
        address _token,
        uint256 _tokenId,
        uint256 _amount
    ) external {
        _recoverERC1155(_token, _tokenId, beneficiary, _amount);
    }

    function _recoverERC20(
        address _token,
        address _recipient,
        uint256 _amount
    ) internal virtual override {
        if (_recipient == LIDO_AGENT) {
            IERC20(_token).safeIncreaseAllowance(LIDO_AGENT, _amount);
            IVault(LIDO_AGENT).deposit(_token, _amount);
            emit ERC20Recovered(_token, LIDO_AGENT, _amount);
        } else {
            super._recoverERC20(_token, _recipient, _amount);
        }
    }

    function _checkBeneficiary() internal {
        require(msg.sender == beneficiary, "Only beneficiary has access");
    }

    function _checkTokensReverseOrder(IERC20 _sellToken, IERC20 _buyToken) internal view returns (bool) {
        if (_sellToken == buyToken && _buyToken == sellToken) {
            return true;
        } else {
            require(sellToken == sellToken, "Unsuported sellToken");
            require(buyToken == buyToken, "Unsuported buyToken");
        }
        return false;
    }
}
