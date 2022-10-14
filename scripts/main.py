from datetime import datetime
from brownie import chain, network, accounts, interface, OTCSeller, OTCRegistry
from brownie.utils import color
from utils.cow import api_create_order, api_get_order_status, api_get_sell_fee
from utils.deployed_state import read_or_update_state
from utils.env import get_env
from utils.helpers import formatUnit, parseUnit
import utils.log as log
from scripts.deploy import (
    deploy_registry,
    deploy_seller,
    get_token_data,
    make_initialize_args,
    make_order,
    make_registry_constructor_args,
)
from utils.config import weth_token_address, lido_dao_agent_address
from otc_seller_config import BENEFICIARY, MAX_MARGIN, CONST_PRICE

# environment
WEB3_INFURA_PROJECT_ID = get_env("WEB3_INFURA_PROJECT_ID")
ETHERSCAN_TOKEN = get_env("ETHERSCAN_TOKEN")


def checkEnv():
    if not WEB3_INFURA_PROJECT_ID:
        log.error("`WEB3_INFURA_PROJECT_ID` env not found!")
        exit()

    if not ETHERSCAN_TOKEN:
        log.error("`ETHERSCAN_TOKEN` env not found!")
        exit()

    log.okay("Environment variables checked")


def loadAccount(accountEnvName):
    accountId = get_env(accountEnvName)
    if not accountId:
        log.error(f"`{accountEnvName}` env not found!")
        return

    try:
        account = accounts.load(accountId)
    except FileNotFoundError:
        log.error(f"Local account with id `{accountId}` not found!")
        exit()

    log.okay(f"`{accountId}` account loaded")
    return account


def proceedPrompt():
    proceed = log.prompt_yes_no("Proceed?")
    if not proceed:
        log.error("Script stopped!")
        exit()


def showTokensPrice(sellTokenAddress, buyTokenAddress, priceFeedAddress):
    [_, sellTokenSymbol, sellTokenDecimals] = get_token_data(sellTokenAddress)
    [_, buyTokenSymbol, buyTokenDecimals] = get_token_data(buyTokenAddress)
    priceFeed = interface.IChainlinkPriceFeedV3(priceFeedAddress)
    priceFeedDecimals = priceFeed.decimals()
    [_, price, _, _, _] = priceFeed.latestRoundData()
    directPrice = price * (10 ** (18 - priceFeedDecimals))
    reversePrice = (10 ** (18 + priceFeedDecimals)) // price

    log.info(f"{color('bright red')}!!! Check price feed response for correctness !!!")
    directAmount = (parseUnit("1", sellTokenDecimals) * directPrice) / (10 ** (18 + sellTokenDecimals - buyTokenDecimals))
    reverseAmount = (parseUnit("1", buyTokenDecimals) * reversePrice) / (10 ** (18 + buyTokenDecimals - sellTokenDecimals))

    log.note(f"Price for 1{sellTokenSymbol}", f"{formatUnit(directAmount, buyTokenDecimals)}{buyTokenSymbol}")
    log.note(f"Price for 1{buyTokenSymbol}", f"{formatUnit(reverseAmount, sellTokenDecimals)}{sellTokenSymbol}")


def deployRegistry(beneficiaryAddress=BENEFICIARY):
    log.info("-= OTCRegistry deploy =-")

    checkEnv()
    deployer = loadAccount("DEPLOYER")

    log.note("NETWORK", network.show_active())
    log.note("DEPLOYER", deployer.address)

    regArgs = make_registry_constructor_args(weth_token=weth_token_address, dao_vault=lido_dao_agent_address, receiver=beneficiaryAddress)

    log.info("> registryConstructorArgs:")
    for k, v in regArgs.items():
        log.note(k, v)

    # args = make_initialize_args(sell_toke=SELL_TOKEN, buy_token=BUY_TOKEN, price_feed=PRICE_FEED, max_margin=MAX_MARGIN, const_price=CONST_PRICE or 0)

    # [_, sellTokenSymbol, _] = get_token_data(SELL_TOKEN)
    # [_, buyTokenSymbol, _] = get_token_data(BUY_TOKEN)
    # log.info("Ready to deploy OTCSeller", f"{sellTokenSymbol}:{buyTokenSymbol}")
    # log.info("> sellerInitializeArgs:")
    # for k, v in args.items():
    #     log.note(k, v)

    # showTokensPrice(SELL_TOKEN, BUY_TOKEN, PRICE_FEED)

    proceedPrompt()

    log.note(f"OTCRegistry deploy")
    registry = deploy_registry({"from": deployer}, regArgs)

    if network.show_active() == "mainnet":
        proceed = log.prompt_yes_no("(Re)Try to publish source codes?")
        if proceed:
            OTCRegistry.publish_source(registry)
            OTCSeller.publish_source(registry.implementation())
            log.okay("Contract source published!")
    else:
        log.info(f"The current network '{network.show_active()}' is not 'mainnet'. Source publication skipped")

    log.note("All deployed metadata saved to", f"./deployed-{network.show_active()}.json")


def deploySeller(sellTokenAddress, buyTokenAddress, priceFeedAddress, maxMargin=MAX_MARGIN, constPrice=CONST_PRICE or 0):
    log.info("-= OTCSeller deploy =-")

    checkEnv()
    deployer = loadAccount("DEPLOYER")

    log.note("NETWORK", network.show_active())
    log.note("DEPLOYER", deployer.address)
    args = make_initialize_args(
        sell_token=sellTokenAddress, buy_token=buyTokenAddress, price_feed=priceFeedAddress, max_margin=maxMargin, const_price=constPrice
    )
    [_, sellTokenSymbol, _] = get_token_data(sellTokenAddress)
    [_, buyTokenSymbol, _] = get_token_data(buyTokenAddress)
    log.info("Ready to deploy OTCSeller", f"{sellTokenSymbol}:{buyTokenSymbol}")
    log.info("> sellerInitializeArgs:")
    for k, v in args.items():
        log.note(k, v)

    showTokensPrice(sellTokenAddress, buyTokenAddress, priceFeedAddress)

    proceedPrompt()

    log.note(f"OTCSeller deploy")
    seller = deploy_seller({"from": deployer}, args)

    log.note("All deployed metadata saved to", f"./deployed-{network.show_active()}.json")


def signOrder(sellTokenAddress, buyTokenAddress, sellAmount, validPeriod=3600):
    log.info("-= Create and sign order =-")

    txExecutor = loadAccount("EXECUTOR")

    deployedState = read_or_update_state()
    if not deployedState.registryAddress:
        log.error("Registry not defined/deployed")
        exit()
    registry = OTCRegistry.at(deployedState.registryAddress)
    log.info(f"Using registry at", registry.address)

    sellerAddress = registry.getSellerFor(sellTokenAddress, buyTokenAddress)
    if not registry.isSellerExists(sellerAddress):
        log.error(f"Seller for pair {sellTokenAddress}:{buyTokenAddress} is not defined/deployed")
        exit()
    log.info(f"Using OTCSeller at", sellerAddress)

    validPeriod = int(validPeriod)
    if validPeriod < 300:
        log.error(f"Order validity time is too small (less than 5min)")
        exit()

    [sellToken, sellTokenSymbol, sellTokenDecimals] = get_token_data(sellTokenAddress)
    [buyToken, buyTokenSymbol, buyTokenDecimals] = get_token_data(buyTokenAddress)
    sellAmount = parseUnit(sellAmount, sellTokenDecimals)

    if sellToken.balanceOf(sellerAddress) < sellAmount:
        log.error(f"Seller balance is below sell amount")
        exit()

    seller = OTCSeller.at(sellerAddress)
    receiver = seller.BENEFICIARY()
    log.info(f"Getting fee amount...")
    feeAmount, buyAmount = api_get_sell_fee(sellTokenAddress, buyTokenAddress, sellAmount, "mainnet")
    validTo = chain.time() + validPeriod
    appData = "0x0000000000000000000000000000000000000000000000000000000000000000"

    log.info("Order ready for sign", f"{sellTokenSymbol} -> {buyTokenSymbol}")
    log.note("sellToken", f"{sellTokenAddress} ({sellTokenSymbol})")
    log.note("buyToken", f"{buyTokenAddress} ({buyTokenSymbol})")
    log.note("sellAmount", f"{formatUnit(sellAmount, sellTokenDecimals)}{sellTokenSymbol}")
    log.note("buyAmount", f"{formatUnit(buyAmount, buyTokenDecimals)}{buyTokenSymbol}")
    log.note("feeAmount", f"{formatUnit(feeAmount, sellTokenDecimals)}{sellTokenSymbol}")
    log.note("validTo", datetime.fromtimestamp(validTo))
    log.note("txExecutor", txExecutor)

    log.info(f"{color('bright red')}!!! Check min buy amount for correctness !!!")
    [price, maxMargin] = registry.getPriceAndMaxMargin(sellTokenAddress, buyTokenAddress)
    buyAmount = ((sellAmount * price * (10000 - maxMargin)) // 10000) // (10 ** (18 + sellTokenDecimals - buyTokenDecimals))
    log.note("Sell amount", f"{formatUnit(sellAmount, sellTokenDecimals)}{sellTokenSymbol}")
    log.note("Min buy amount", f"{formatUnit(buyAmount, buyTokenDecimals)}{buyTokenSymbol}")

    proceedPrompt()

    log.info("Checking order...")
    order = make_order(
        sell_token=sellTokenAddress,
        buy_token=buyTokenAddress,
        receiver=receiver,
        sell_amount=sellAmount,
        buy_amount=buyAmount,
        valid_to=validTo,
        app_data=appData,
        fee_amount=feeAmount,
        partiallyFillable=False,
    )
    orderUidCalculated = seller.getOrderUid(order)
    if not seller.checkOrder(order, orderUidCalculated):
        log.error(f"Check order failed!")
        exit()
    log.okay("Order is correct")
    log.info("Creating CowSwap order (via API)...")
    orderUid = api_create_order(
        sell_token=sellTokenAddress,
        buy_token=buyTokenAddress,
        sell_amount=sellAmount,
        buy_amount=buyAmount,
        fee_amount=feeAmount,
        valid_to=validTo,
        sender=sellerAddress,
        receiver=receiver,
        partiallyFillable=False,
        app_data=appData,
        network="mainnet",
    )

    if orderUid != orderUidCalculated:
        log.error(f"OrderUid mismatch")
        exit()

    log.okay("CowSwap order created, orderUid", orderUid)
    log.info("Check order status...")
    status = api_get_order_status(orderUid, "mainnet")
    log.note("Order status", status)
    if status != "presignaturePending":
        log.error("Wrong order status, aborting...")
        exit()

    log.info("Sending sign order tx...")
    tx = seller.signOrder(order, orderUid, {"from": txExecutor})
    assert "OrderSigned" in tx.events
    assert tx.events["OrderSigned"]["orderUid"] == orderUid
    assert "PreSignature" in tx.events
    assert tx.events["PreSignature"]["orderUid"] == orderUid
    assert tx.events["PreSignature"]["signed"] == True

    log.info("> txHash:", tx.txid)
    log.okay("Order signed")
