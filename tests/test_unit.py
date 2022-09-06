import pytest
from brownie import reverts, Wei, web3

from utils.config import (
    eth_token_address,
    usdc_token_address,
    usdt_token_address,
    steth_token_address,
    ldo_token_address,
    weth_token_address,
    dai_token_address,
    lido_dao_agent_address,
    chainlink_dai_eth,
    chainlink_usdt_eth,
    chainlink_usdc_eth,
    chainlink_ldo_eth,
    chainlink_steth_eth,
    DEFAULT_ADMIN_ROLE,
    ORDER_SETTLE_ROLE,
    OPERATOR_ROLE,
    PRE_SIGNED,
)

from scripts.deploy import get_setup_state


@pytest.fixture
def simulate_order_settle(accounts, seller_dev, sell_amount):
    def run():
        dao_agent_account = accounts.at(lido_dao_agent_address, force=True)
        # simulate ETH transfer from Agent to Seller
        dao_agent_account.transfer(seller_dev.address, sell_amount)

    return run


@pytest.fixture
def simulate_order_fulfill(accounts, seller_dev, sell_amount, buy_amount, cow_settlement, dai_token, weth_token):
    def run(orderUid):
        seller_account = accounts.at(seller_dev.address, force=True)
        dai_holder = accounts.at("0x075e72a5eDf65F0A5f44699c7654C1a76941Ddc8", force=True)
        # ugly hack to simulate order fulfill by DAI
        # invalidateOrder can be called only by order owner and sets filledAmount[orderUid] = -1
        # so the Seller contract assumes that order is filled
        cow_settlement.invalidateOrder(orderUid, {"from": seller_account})
        # simulating DAI transfer
        dai_token.transfer(seller_dev.address, buy_amount, {"from": dai_holder})
        # simulate WETH transfer
        weth_token.transfer(dai_holder.address, sell_amount, {"from": seller_account})

    return run


@pytest.fixture
def settled_order(accounts, seller_dev, order_sell_eth_for_dai, simulate_order_settle):
    order = order_sell_eth_for_dai(seller_dev)
    orderUid = seller_dev.getOrderUid(order)

    simulate_order_settle()
    tx = seller_dev.settleOrderETHForDAI(order, orderUid, {"from": accounts[0]})
    return (order, orderUid, tx)


def test_non_finalized_deploy_params(accounts, setup_and_seller_non_finalized):
    (setup, seller) = setup_and_seller_non_finalized
    deployer = accounts[0]
    assert seller.LIDO_AGENT() == lido_dao_agent_address
    assert seller.TOKEN_DAI() == dai_token_address
    assert seller.TOKEN_WETH() == weth_token_address
    assert seller.TOKEN_USDC() == usdc_token_address
    assert seller.TOKEN_USDT() == usdt_token_address
    assert seller.TOKEN_LDO() == ldo_token_address
    assert seller.TOKEN_STETH() == steth_token_address
    assert seller.CHAINLINK_DAI_ETH() == chainlink_dai_eth
    assert seller.CHAINLINK_USDT_ETH() == chainlink_usdt_eth
    assert seller.CHAINLINK_USDC_ETH() == chainlink_usdc_eth
    assert seller.CHAINLINK_LDO_ETH() == chainlink_ldo_eth
    assert seller.CHAINLINK_STETH_ETH() == chainlink_steth_eth

    setupState = get_setup_state(setup)
    assert setupState.lastSetupStatus == "Deployed"
    assert setupState.deployerAddress == deployer

    assert setup.SLIPPAGE() == seller.getSlippage()

    assert seller.getRoleMemberCount(DEFAULT_ADMIN_ROLE) == 2
    assert seller.getRoleMemberCount(ORDER_SETTLE_ROLE) == 2
    assert seller.getRoleMemberCount(OPERATOR_ROLE) == 2

    assert seller.getRoleMember(OPERATOR_ROLE, 0) == lido_dao_agent_address
    assert seller.getRoleMember(ORDER_SETTLE_ROLE, 0) == lido_dao_agent_address

    assert seller.getRoleMember(OPERATOR_ROLE, 1) == deployer
    assert seller.getRoleMember(ORDER_SETTLE_ROLE, 1) == deployer

    with reverts():
        setup.check({"from": accounts[0]})


def test_finalized_deploy_params(accounts, setup_and_seller_finalized):
    (setup, seller) = setup_and_seller_finalized
    deployer = accounts[0]
    assert seller.LIDO_AGENT() == lido_dao_agent_address
    assert seller.TOKEN_DAI() == dai_token_address
    assert seller.TOKEN_WETH() == weth_token_address
    assert seller.TOKEN_USDC() == usdc_token_address
    assert seller.TOKEN_USDT() == usdt_token_address
    assert seller.TOKEN_LDO() == ldo_token_address
    assert seller.TOKEN_STETH() == steth_token_address
    assert seller.CHAINLINK_DAI_ETH() == chainlink_dai_eth
    assert seller.CHAINLINK_USDT_ETH() == chainlink_usdt_eth
    assert seller.CHAINLINK_USDC_ETH() == chainlink_usdc_eth
    assert seller.CHAINLINK_LDO_ETH() == chainlink_ldo_eth
    assert seller.CHAINLINK_STETH_ETH() == chainlink_steth_eth

    setupState = get_setup_state(setup)
    assert setupState.lastSetupStatus == "Finalized"
    assert setupState.deployerAddress == deployer

    assert setup.SLIPPAGE() == seller.getSlippage()

    assert seller.getRoleMemberCount(DEFAULT_ADMIN_ROLE) == 1
    assert seller.getRoleMemberCount(ORDER_SETTLE_ROLE) == 1
    assert seller.getRoleMemberCount(OPERATOR_ROLE) == 1

    assert seller.getRoleMember(OPERATOR_ROLE, 0) == lido_dao_agent_address
    assert seller.getRoleMember(ORDER_SETTLE_ROLE, 0) == lido_dao_agent_address

    assert setup.check({"from": accounts[0]}) == True


def test_get_swap_price(seller, sell_amount):
    best_price = seller.getBestSwapPrice(weth_token_address, dai_token_address, sell_amount)
    assert best_price > 0


def test_get_chainlink_price(seller):
    chainlink_price = seller.getChainlinkReversePrice(chainlink_dai_eth)
    assert chainlink_price > 0


def test_settle_order(
    accounts,
    seller_dev,
    settled_order,
    sell_token,
    buy_token,
    sell_amount,
    buy_amount,
    weth_token,
    cow_settlement,
):
    (_, orderUid, tx) = settled_order

    assert "OrderSettled" in tx.events
    assert tx.events["OrderSettled"]["orderUid"] == orderUid
    assert "PreSignature" in tx.events
    assert tx.events["PreSignature"]["orderUid"] == orderUid
    assert tx.events["PreSignature"]["signed"] == True

    assert weth_token.balanceOf(seller_dev.address) == sell_amount
    assert cow_settlement.preSignature(orderUid) == PRE_SIGNED
    assert seller_dev.getSellTokenReservedAmount(sell_token) == sell_amount

    [order_state, order_sell_token, order_buy_token, order_sell_amount, order_buy_amount] = seller_dev.getOrder(orderUid)
    assert order_state == 1  # Settled
    assert order_sell_token == sell_token
    assert order_buy_token == buy_token
    assert order_sell_amount == sell_amount
    assert order_buy_amount == buy_amount


def test_cancel_order(accounts, settled_order, sell_token, seller_dev, sell_amount, weth_token, cow_settlement):
    (_, orderUid, tx) = settled_order

    agentBalanceETH = web3.eth.get_balance(lido_dao_agent_address)
    tx = seller_dev.cancelOrder(orderUid, {"from": accounts[0]})

    assert "OrderCanceled" in tx.events
    assert tx.events["OrderCanceled"]["orderUid"] == orderUid
    assert "VaultDeposit" in tx.events
    assert tx.events["VaultDeposit"]["token"] == eth_token_address
    assert tx.events["VaultDeposit"]["amount"] == sell_amount
    assert "PreSignature" in tx.events
    assert tx.events["PreSignature"]["orderUid"] == orderUid
    assert tx.events["PreSignature"]["signed"] == False

    assert web3.eth.get_balance(lido_dao_agent_address) == agentBalanceETH + sell_amount
    assert weth_token.balanceOf(seller_dev.address) == 0
    assert cow_settlement.preSignature(orderUid) == 0
    assert seller_dev.getSellTokenReservedAmount(sell_token) == 0

    [order_state, *_] = seller_dev.getOrder(orderUid)
    assert order_state == 3  # Canceled


def test_complete_order(accounts, settled_order, sell_token, buy_token, seller_dev, buy_amount, weth_token, dai_token, simulate_order_fulfill):
    (_, orderUid, tx) = settled_order

    agentBalanceDAI = dai_token.balanceOf(lido_dao_agent_address)
    with reverts("TokenSeller: order not yet filled"):
        seller_dev.completeOrder(orderUid, {"from": accounts[0]})

    simulate_order_fulfill(orderUid)

    # call complete order to make deposit to Agent
    tx = seller_dev.completeOrder(orderUid, {"from": accounts[0]})
    print(tx.events)
    assert "OrderCompleted" in tx.events
    assert tx.events["OrderCompleted"]["orderUid"] == orderUid
    assert "VaultDeposit" in tx.events
    assert tx.events["VaultDeposit"]["token"] == buy_token
    assert tx.events["VaultDeposit"]["amount"] == buy_amount

    assert dai_token.balanceOf(lido_dao_agent_address) == agentBalanceDAI + buy_amount
    assert weth_token.balanceOf(seller_dev.address) == 0
    assert seller_dev.getSellTokenReservedAmount(sell_token) == 0

    [order_state, *_] = seller_dev.getOrder(orderUid)
    assert order_state == 2  # Completed
