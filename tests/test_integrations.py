import pytest
from brownie import chain, Wei, web3

from utils.cow import api_create_order
from utils.config import chainlink_dai_eth, PRE_SIGNED


def test_get_quotes(seller, sell_token, buy_token, sell_amount, buy_amount, fee_amount):
    slippage = seller.getSlippage()
    maxSlippage = seller.MAX_SLIPPAGE()
    worst_buy_amount = buy_amount * (10000 - maxSlippage) / 10000 / 10**18

    # ensure the CowSwap offer is not worse than exchange on curve.fi
    best_price = seller.getBestSwapPrice(sell_token, buy_token, 10**18)
    best_buy_amount = best_price * sell_amount * (10000 - slippage) / 10000 / 10**18
    assert best_buy_amount <= buy_amount and best_buy_amount >= worst_buy_amount

    # ensure the CowSwap offer is not worse than chainlink price
    chainlink_price = seller.getChainlinkReversePrice(chainlink_dai_eth)
    chainlink_buy_amount = chainlink_price * sell_amount * (10000 - slippage) / 10000 / 10**18

    assert chainlink_buy_amount <= buy_amount and chainlink_buy_amount >= worst_buy_amount



def test_create_and_check_order(
    seller, sell_token, buy_token, sell_amount, buy_amount, fee_amount, valid_to, appData, partiallyFillable, order_sell_eth_for_dai
):
    # creating order via CowSwap API
    orderUid = api_create_order(
        sell_token=sell_token,
        buy_token=buy_token,
        sell_amount=sell_amount,
        buy_amount=buy_amount,
        fee_amount=fee_amount,
        valid_to=valid_to,
        sender=seller.address,
        receiver=seller.address,
        partiallyFillable=partiallyFillable,
        appData=appData,
        network="mainnet",
    )
    order = order_sell_eth_for_dai(seller)
    assert orderUid == seller.getOrderUid(order)
    assert seller.checkOrderETHForDAI(order, orderUid) == True


def test_settle_order(seller, sell_amount, order_sell_eth_for_dai, settle_order_and_pass_dao_vote, weth_token, cow_settlement):
    order = order_sell_eth_for_dai(seller)

    # skipping real order place and get orderUid directly
    orderUid = seller.getOrderUid(order)

    settle_order_and_pass_dao_vote(seller, orderUid)

    assert weth_token.balanceOf(seller.address) == sell_amount
    assert cow_settlement.preSignature(orderUid) == PRE_SIGNED


# def test_cancel_order(seller, order_sell_eth_for_dai, settle_order_and_pass_dao_vote, cow_settlement):
#     order = order_sell_eth_for_dai(seller)
#     # skipping real order place and get orderUid directly
#     orderUid = seller.getOrderUid(order)

#     settle_order_and_pass_dao_vote(seller, orderUid)

#     PRE_SIGNED = web3.keccak(text="GPv2Signing.Scheme.PreSign").hex() 
#     assert cow_settlement.preSignature(orderUid) == PRE_SIGNED


