from dotmap import DotMap
from utils.deployed_state import read_or_update_state
import utils.log as log
from utils.cow import KIND_SELL, BALANCE_ERC20, api_get_sell_fee, api_create_order

try:
    from brownie import OTCSeller, interface, Wei
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

from otc_seller_config import SLIPPAGE, TOTAL_ETH_TO_SELL


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
            encode_agent_execute(target=weth.address, call_value=sell_amount, call_data=weth_deposit_calldata, agent=agent),
            encode_token_transfer(
                token_address=weth_token_address,  # NOTE: in case of ETH, token address here must be 0x0000000000000000000000000000000000000000
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


def make_constructor_args(sell_toke, buy_token, price_feed, receiver, max_slippage):
        return DotMap({
            "sellTokenAddress": sell_toke,
            "buyTokenAddress": buy_token,
            "chainLinkPriceFeedAddress": price_feed,
            "beneficiaryAddress": receiver,
            "maxSlippage": max_slippage,
        })

def deploy(tx_params, constructorArgs):
    deployedState = read_or_update_state()

    if deployedState.sellerAddress:
        log.warn("Seller already deployed at", deployedState.sellerAddress)
        seller = OTCSeller.at(deployedState.sellerAddress)
    else:
        log.info("Deploying OTCSeller...")
        args = DotMap(constructorArgs)
        seller = OTCSeller.deploy(
            args.sellTokenAddress,
            args.buyTokenAddress,
            args.chainLinkPriceFeedAddress,
            args.beneficiaryAddress,
            args.maxSlippage,
            tx_params,
        )
        log.info("> txHash:", seller.tx.txid)
        deployedState = read_or_update_state(
            {
                "deployer": tx_params["from"].address,
                "sellerDeployTx": seller.tx.txid,
                "sellerAddress": seller.address,
                "sellerDeployConstructorArgs": args.toDict(),
            }
        )
        log.okay("OTCSeller deployed at", seller.address)

    return seller

def check_deployed(seller, constructorArgs):
    assert seller.LIDO_AGENT() == lido_dao_agent_address, "Wrong Lido Agent address"
    assert seller.WETH() == weth_token_address, "Wrong WETH address"
    assert seller.sellToken() == constructorArgs.sellTokenAddress, "Wrong sellToken address"
    assert seller.buyToken() == constructorArgs.buyTokenAddress, "Wrong buyToken address"
    assert seller.beneficiary() == constructorArgs.beneficiaryAddress, "Wrong beneficiary address"
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
