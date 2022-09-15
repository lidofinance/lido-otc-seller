from dotmap import DotMap
from utils.deployed_state import read_or_update_state
import utils.log as log
from utils.cow import KIND_SELL, BALANCE_ERC20, api_get_sell_fee, api_create_order

try:
    from brownie import OTCSeller, OTCRegistry, interface, Wei
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


def make_constructor_args(sell_toke, buy_token, price_feed, max_slippage):
    return DotMap(
        {
            "sellTokenAddress": sell_toke,
            "buyTokenAddress": buy_token,
            "chainLinkPriceFeedAddress": price_feed,
            # "beneficiaryAddress": receiver,
            "maxSlippage": max_slippage,
        }
    )


def make_registry_constructor_args(weth_token, dao_vault, receiver):
    return DotMap(
        {
            "wethAddress": weth_token,
            "daoVaultAddress": dao_vault,
            "beneficiaryAddress": receiver,
        }
    )


def deploy_registry(tx_params, constructorArgs):
    deployedState = read_or_update_state()

    if deployedState.registryAddress:
        log.warn("OTCRegistry already deployed at", deployedState.registryAddress)
        registry = OTCRegistry.at(deployedState.registryAddress)
    else:
        log.info("Deploying OTCRegistry...")
        args = DotMap(constructorArgs)
        registry = OTCRegistry.deploy(
            args.wethAddress,
            args.daoVaultAddress,
            args.beneficiaryAddress,
            tx_params,
        )
        log.info("> txHash:", registry.tx.txid)
        implementationAddress = registry.implementation()
        deployedState = read_or_update_state(
            {
                "deployer": tx_params["from"].address,
                "registryDeployTx": registry.tx.txid,
                "registryAddress": registry.address,
                "registryDeployConstructorArgs": args.toDict(),
                "implementationAddress": implementationAddress,
            }
        )
        log.okay("OTCRegistry deployed at", registry.address)

    return registry


def deploy(tx_params, registryConstructorArgs, constructorArgs):
    # deployedState = read_or_update_state()
    registry = deploy_registry(tx_params, registryConstructorArgs)

    args = DotMap(constructorArgs)
    seller_address = registry.getSellerFor(args.sellTokenAddress, args.buyTokenAddress)
    if (not registry.isSellerExists(seller_address)):
        log.info(f"Deploying OTCSeller for tokens pair {args.sellTokenAddress}:{args.buyTokenAddress}...")
        args = DotMap(constructorArgs)
        tx = registry.createSeller(
            args.sellTokenAddress,
            args.buyTokenAddress,
            args.chainLinkPriceFeedAddress,
            args.maxSlippage,
            tx_params,
        )
        log.info("> txHash:", tx.txid)
        deployedState = read_or_update_state(
            {
                "seller0DeployTx": tx.txid,
                "seller0Address": seller_address,
                "seller0DeployConstructorArgs": args.toDict(),
            }
        )
        log.okay("OTCSeller deployed at", seller_address)
    else:
        log.warn("Seller already deployed at", seller_address)
    seller = OTCSeller.at(seller_address)

    return (registry, seller)


def check_deployed(registry, seller, registryConstructorArgs, constructorArgs):
    assert registry.isSellerExists(seller.address) == True, "Incorrect seller deploy"
    assert seller.DAO_VAULT() == registryConstructorArgs.daoVaultAddress, "Wrong Lido Agent address"
    assert seller.WETH() == registryConstructorArgs.wethAddress, "Wrong WETH address"
    assert seller.sellToken() == constructorArgs.sellTokenAddress, "Wrong sellToken address"
    assert seller.buyToken() == constructorArgs.buyTokenAddress, "Wrong buyToken address"
    assert seller.BENEFICIARY() == registryConstructorArgs.beneficiaryAddress, "Wrong beneficiary address"
    assert seller.priceFeed() == constructorArgs.chainLinkPriceFeedAddress, "Wrong ChainLink price feed address"
    assert seller.maxSlippage() == constructorArgs.maxSlippage, "Wrong max slippage"


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
