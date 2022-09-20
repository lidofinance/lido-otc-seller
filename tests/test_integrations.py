import pytest
from brownie import chain, Wei, reverts

from utils.cow import api_create_order, api_get_sell_fee
from utils.config import weth_token_address, dai_token_address, lido_dao_agent_address, cowswap_vault_relayer, PRE_SIGNED
from otc_seller_config import MAX_MARGIN

SELL_AMOUNT = Wei("10000 ether")


@pytest.fixture
def sell_amount():
    return SELL_AMOUNT


@pytest.fixture
def registry_and_seller(deploy_seller_eth_for_dai):
    return deploy_seller_eth_for_dai(receiver=lido_dao_agent_address, max_margin=MAX_MARGIN)


@pytest.fixture
def seller(registry_and_seller):
    (_, seller) = registry_and_seller
    return seller


@pytest.fixture
def registry(registry_and_seller):
    (registry, _) = registry_and_seller
    return registry


@pytest.fixture
def fee_buy_amount():
    def run(sell_token, buy_token, sell_amount):
        return api_get_sell_fee(sell_token, buy_token, sell_amount, "mainnet")

    return run


def test_get_quotes(seller, sell_amount, fee_buy_amount):
    sell_token = weth_token_address
    buy_token = dai_token_address
    fee_amount, buy_amount = fee_buy_amount(sell_token=sell_token, buy_token=buy_token, sell_amount=sell_amount)

    # ensure the CowSwap offer is not worse than chainlink price
    # note: in the case of selling ETH for DAI, we should use reverse price
    # as the chainlink price feed returns the ETH amount for 1DAI
    (chainlink_price, max_margin) = seller.priceAndMaxMargin()
    # TODO: use token decimals
    chainlink_buy_amount = chainlink_price * sell_amount * (10000 - max_margin) / 10000 / 10**18
    assert chainlink_buy_amount <= buy_amount and chainlink_buy_amount > 0


def test_create_and_check_order(seller, sell_amount, app_data, make_order_sell_weth_for_dai, fee_buy_amount):
    sell_token = weth_token_address
    buy_token = dai_token_address
    fee_amount, buy_amount = fee_buy_amount(sell_token=sell_token, buy_token=buy_token, sell_amount=sell_amount)
    valid_to = chain.time() + 300  # 5m
    # creating dummy 5min order via CowSwap API
    orderUid = api_create_order(
        sell_token=sell_token,
        buy_token=buy_token,
        sell_amount=sell_amount,
        buy_amount=buy_amount,
        fee_amount=fee_amount,
        valid_to=valid_to,
        sender=seller.address,
        receiver=lido_dao_agent_address,
        partiallyFillable=False,
        app_data=app_data,
        network="mainnet",
    )
    order = make_order_sell_weth_for_dai(
        sell_amount=sell_amount, buy_amount=buy_amount, fee_amount=fee_amount, receiver=lido_dao_agent_address, valid_to=valid_to
    )
    assert orderUid == seller.getOrderUid(order)
    assert seller.checkOrder(order, orderUid) == True


def test_settle_order(
    accounts, seller, sell_amount, fee_buy_amount, make_order_sell_weth_for_dai, transfer_eth_for_sell_and_pass_dao_vote, weth_token, cow_settlement
):

    transfer_eth_for_sell_and_pass_dao_vote(seller=seller, sell_amount=sell_amount)
    assert weth_token.balanceOf(seller.address) == sell_amount

    sell_token = weth_token_address
    buy_token = dai_token_address
    fee_amount, buy_amount = fee_buy_amount(sell_token=sell_token, buy_token=buy_token, sell_amount=sell_amount)
    valid_to = chain.time() + 3600  # 1h
    order = make_order_sell_weth_for_dai(
        sell_amount=sell_amount, buy_amount=buy_amount, fee_amount=fee_amount, receiver=lido_dao_agent_address, valid_to=valid_to
    )

    # skipping real order place and get orderUid directly
    orderUid = seller.getOrderUid(order)

    allowanceBefore = weth_token.allowance(seller.address, cowswap_vault_relayer)
    tx = seller.settleOrder(order, orderUid, {"from": accounts[0]})

    assert weth_token.allowance(seller.address, cowswap_vault_relayer) >= allowanceBefore + sell_amount
    assert cow_settlement.preSignature(orderUid) == PRE_SIGNED

    assert "OrderSettled" in tx.events
    assert tx.events["OrderSettled"]["orderUid"] == orderUid
    assert "PreSignature" in tx.events
    assert tx.events["PreSignature"]["orderUid"] == orderUid
    assert tx.events["PreSignature"]["signed"] == True


def test_cancel_order(
    accounts, seller, sell_amount, fee_buy_amount, make_order_sell_weth_for_dai, transfer_eth_for_sell_and_pass_dao_vote, weth_token, cow_settlement
):
    transfer_eth_for_sell_and_pass_dao_vote(seller=seller, sell_amount=sell_amount)

    sell_token = weth_token_address
    buy_token = dai_token_address
    fee_amount, buy_amount = fee_buy_amount(sell_token=sell_token, buy_token=buy_token, sell_amount=sell_amount)
    valid_to = chain.time() + 3600  # 1h
    order = make_order_sell_weth_for_dai(
        sell_amount=sell_amount, buy_amount=buy_amount, fee_amount=fee_amount, receiver=lido_dao_agent_address, valid_to=valid_to
    )

    # skipping real order place and get orderUid directly
    orderUid = seller.getOrderUid(order)

    tx = seller.settleOrder(order, orderUid, {"from": accounts[0]})
    with reverts():
        seller.cancelOrder(orderUid, {"from": accounts[0]})

    dao_agent_account = accounts.at(lido_dao_agent_address, force=True)
    tx = seller.cancelOrder(orderUid, {"from": dao_agent_account})
    assert "OrderCanceled" in tx.events
    assert tx.events["OrderCanceled"]["orderUid"] == orderUid
    assert "PreSignature" in tx.events
    assert tx.events["PreSignature"]["orderUid"] == orderUid
    assert tx.events["PreSignature"]["signed"] == False

    assert cow_settlement.preSignature(orderUid) == 0
