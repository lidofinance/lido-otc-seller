from dotmap import DotMap
from utils.deployed_state import read_or_update_state
import utils.log as log
from utils.cow import KIND_SELL, BALANCE_ERC20

try:
    from brownie import OTCSeller, OTCFactory, interface, Wei
except ImportError:
    print("You're probably running inside Brownie console. Please call:")
    print("set_console_globals(interface=interface, PurchaseExecutor=PurchaseExecutor)")


def set_console_globals(**kwargs):
    global Setup
    global OTCSeller
    global interface
    OTCSeller = kwargs["OTCSeller"]
    interface = kwargs["interface"]


from utils.dao import create_vote, encode_token_transfer, encode_call_script, encode_agent_execute, encode_wrap_eth

from utils.config import (
    eth_token_address,
    weth_token_address,
    dai_token_address,
    lido_dao_agent_address,
    lido_dao_voting_address,
    lido_dao_finance_address,
    lido_dao_token_manager_address,
)


def propose_transfer_eth_for_sell(
    tx_params,
    seller_address,
    sell_amount,
    reference,
):

    agent = interface.Agent(lido_dao_agent_address)
    voting = interface.Voting(lido_dao_voting_address)
    finance = interface.Finance(lido_dao_finance_address)
    token_manager = interface.TokenManager(lido_dao_token_manager_address)
    weth = interface.WETH(weth_token_address)
    # seller = OTCSeller.at(seller_address)

    _, weth_deposit_calldata = encode_wrap_eth(weth)
    evm_script = encode_call_script(
        [
            # 1st, wrapping ETH to WETH
            encode_agent_execute(target=weth.address, call_value=sell_amount, call_data=weth_deposit_calldata, agent=agent),
            # 2nd, sending WETH to Seller
            encode_token_transfer(
                token_address=weth_token_address,
                receiver=seller_address,
                amount=sell_amount,
                reference=reference,
                finance=finance,
            ),
        ]
    )
    return create_vote(
        voting=voting,
        token_manager=token_manager,
        vote_desc=f"Sell {Wei(sell_amount).to('ether')} ETH for DAI, Seller contract: {seller_address}",
        evm_script=evm_script,
        tx_params=tx_params,
    )


def make_initialize_args(receiver, sell_token, buy_token, price_feed, max_margin, const_price):
    return DotMap(
        {
            "beneficiaryAddress": receiver,
            "sellTokenAddress": sell_token,
            "buyTokenAddress": buy_token,
            "chainLinkPriceFeedAddress": price_feed,
            "maxMargin": max_margin,
            "constantPrice": const_price,
        }
    )


def make_factory_constructor_args(weth_token, dao_vault):
    return DotMap({"wethAddress": weth_token, "daoVaultAddress": dao_vault})


def deploy_factory(tx_params, sellerInitializeArgs):
    deployedState = read_or_update_state()

    if deployedState.factoryAddress:
        factory = OTCFactory.at(deployedState.factoryAddress)
        log.warn("OTCFactory already deployed at", deployedState.factoryAddress)
    else:
        log.info("Deploying OTCFactory...")
        args = DotMap(sellerInitializeArgs)
        factory = OTCFactory.deploy(
            args.wethAddress,
            args.daoVaultAddress,
            tx_params,
        )
        log.info("> txHash:", factory.tx.txid)
        implementationAddress = factory.implementation()
        deployedState = read_or_update_state(
            {
                "deployer": tx_params["from"].address,
                "factoryDeployTx": factory.tx.txid,
                "factoryAddress": factory.address,
                "factoryDeployConstructorArgs": args.toDict(),
                "implementationAddress": implementationAddress,
            }
        )
        log.okay("OTCFactory deployed at", factory.address)

        log.info("Checking deployed OTCFactory...")
        check_deployed_factory(factory=factory, factoryConstructorArgs=args)
        log.okay("OTCFactory check pass")

    return factory


def find_deployed_seller_index(sellers, sellerAddress):
    for index, x in enumerate(sellers):
        if x.sellerAddress == sellerAddress:
            return index
    return -1


def get_token_data(tokenAddress):
    token = interface.ERC20(tokenAddress)
    decimals = token.decimals()
    symbol = token.symbol()
    return (token, symbol, decimals)


def deploy_seller(tx_params, sellerInitializeArgs, factoryAddress=None):
    deployedState = read_or_update_state()
    if not factoryAddress:
        if not deployedState.factoryAddress:
            log.error("Factory is not defined/deployed")
            exit()
        factoryAddress = deployedState.factoryAddress
    factory = OTCFactory.at(factoryAddress)
    log.info(f"Using factory at", factoryAddress)

    args = DotMap(sellerInitializeArgs)
    sellerAddress = factory.getSellerFor(args.beneficiaryAddress, args.sellTokenAddress, args.buyTokenAddress)
    sellers = deployedState.sellers or []
    sellerIndex = find_deployed_seller_index(sellers, sellerAddress)
    if sellerIndex == -1:
        sellerInfo = DotMap({"sellerAddress": sellerAddress})
        sellerIndex = len(sellers)
        sellers.append(sellerInfo)
    else:
        sellerInfo = DotMap(sellers[sellerIndex])

    [_, sellTokenASymbol, _] = get_token_data(args.sellTokenAddress)
    [_, buyTokenBSymbol, _] = get_token_data(args.buyTokenAddress)
    if factory.isSellerExists(sellerAddress):
        log.warn(f"Seller for {sellTokenASymbol}:{buyTokenBSymbol} already deployed at", sellerAddress)
    else:
        log.info("Deploying OTCSeller for tokens pair", f"{sellTokenASymbol}:{buyTokenBSymbol}")

        tx = factory.createSeller(
            args.beneficiaryAddress,
            args.sellTokenAddress,
            args.buyTokenAddress,
            args.chainLinkPriceFeedAddress,
            args.maxMargin,
            args.constantPrice,
            tx_params,
        )
        log.info("> txHash:", tx.txid)
        log.okay("OTCSeller deployed at", sellerAddress)
        sellerInfo.sellerDeployTx = tx.txid
        sellerInfo.sellerDeployConstructorArgs = (args.toDict(),)

    seller = OTCSeller.at(sellerAddress)

    log.info("Checking deployed OTCSeller...")
    check_deployed_seller(factory=factory, seller=seller, sellerInitializeArgs=args)
    log.okay("OTCSeller check pass")

    log.info("Updating seller deployed info...")
    [priceFeed, maxMargin, _, constantPrice] = seller.getPairConfig()
    sellerInfo.pairConfig = {
        "chainLinkPriceFeedAddress": priceFeed,
        "maxMargin": maxMargin,
        "constantPrice": constantPrice,
    }
    sellerInfo.tokenA = seller.tokenA()
    [_, sellerInfo.tokenASymbol, _] = get_token_data(sellerInfo.tokenA)
    sellerInfo.tokenB = seller.tokenB()
    [_, sellerInfo.tokenBSymbol, _] = get_token_data(sellerInfo.tokenB)

    sellers[sellerIndex] = sellerInfo
    deployedState = read_or_update_state(
        {
            "sellers": sellers,
        }
    )

    return seller


# def deploy(tx_params, factoryConstructorArgs, sellerInitializeArgs):
#     factory = deploy_factory(tx_params, factoryConstructorArgs)
#     seller = deploy_seller(tx_params, sellerInitializeArgs)
#     return (factory, seller)


def check_deployed_factory(factory, factoryConstructorArgs):
    impl = OTCSeller.at(factory.implementation())
    assert impl.DAO_VAULT() == factoryConstructorArgs.daoVaultAddress, "Wrong Lido Agent address"
    assert impl.WETH() == factoryConstructorArgs.wethAddress, "Wrong WETH address"


def check_deployed_seller(factory, seller, sellerInitializeArgs):
    assert factory.isSellerExists(seller.address) == True, "Incorrect seller deploy"
    assert (
        factory.getSellerFor(sellerInitializeArgs.beneficiaryAddress, sellerInitializeArgs.sellTokenAddress, sellerInitializeArgs.buyTokenAddress)
        == seller.address
    ), "Incorrect seller deploy"
    assert (
        factory.getSellerFor(sellerInitializeArgs.beneficiaryAddress, sellerInitializeArgs.buyTokenAddress, sellerInitializeArgs.sellTokenAddress)
        == seller.address
    ), "Incorrect seller deploy"

    impl = OTCSeller.at(factory.implementation())

    assert seller.DAO_VAULT() == impl.DAO_VAULT(), "Wrong Lido Agent address on seller"
    assert seller.WETH() == impl.WETH(), "Wrong WETH address on seller"
    assert seller.beneficiary() == sellerInitializeArgs.beneficiaryAddress, "beneficiary address on seller"
    assert seller.tokenA() == sellerInitializeArgs.sellTokenAddress, "Wrong sellToken address"
    assert seller.tokenB() == sellerInitializeArgs.buyTokenAddress, "Wrong buyToken address"

    (priceFeed, maxMargin, _, constPrice) = seller.getPairConfig()
    assert priceFeed == sellerInitializeArgs.chainLinkPriceFeedAddress, "Wrong ChainLink price feed address"
    assert maxMargin == sellerInitializeArgs.maxMargin, "Wrong max priceMargin"
    assert constPrice == sellerInitializeArgs.constantPrice, "Wrong max constantPrice"


def start_dao_vote_transfer_eth_for_sell(tx_params, seller_address, sell_amount):
    (vote_id, _) = propose_transfer_eth_for_sell(
        tx_params=tx_params,
        seller_address=seller_address,
        sell_amount=sell_amount,
        reference=f"Transfer ETH to be sold for DAI",
    )
    return vote_id


def make_order(sell_token, buy_token, receiver, sell_amount, buy_amount, valid_to, app_data, fee_amount, partiallyFillable=False):
    return [
        sell_token,
        buy_token,
        receiver,
        int(sell_amount),
        int(buy_amount),
        valid_to,
        app_data,
        int(fee_amount),
        KIND_SELL,
        partiallyFillable,
        BALANCE_ERC20,
        BALANCE_ERC20,
    ]
