import pytest
from brownie import chain, reverts, Wei, OTCSeller
from scripts.deploy import check_deployed

from utils.config import lido_dao_agent_address, cowswap_vault_relayer, PRE_SIGNED, chainlink_dai_eth, weth_token_address, dai_token_address
from otc_seller_config import MAX_SLIPPAGE

SELL_AMOUNT = Wei("100 ether")


@pytest.fixture
def sell_amount():
    return SELL_AMOUNT


@pytest.fixture
def registry_and_seller(beneficiary, deploy_seller_eth_for_dai):
    return deploy_seller_eth_for_dai(receiver=beneficiary, max_slippage=MAX_SLIPPAGE)


@pytest.fixture
def seller(registry_and_seller):
    (_, seller) = registry_and_seller
    return seller


@pytest.fixture
def registry(registry_and_seller):
    (registry, _) = registry_and_seller
    return registry


@pytest.fixture
def simulate_seller_refill(accounts, seller, weth_token):
    def run(sell_amount):
        dao_agent_account = accounts.at(lido_dao_agent_address, force=True)
        # simulate ETH transfer from Agent to Seller
        dao_agent_account.transfer(seller.address, sell_amount)
        assert weth_token.balanceOf(seller.address) >= sell_amount

    return run


# @pytest.fixture
# def simulate_order_fulfill(accounts, seller_dev, sell_amount, buy_amount, cow_settlement, dai_token, weth_token):
#     def run(orderUid):
#         seller_account = accounts.at(seller_dev.address, force=True)
#         dai_holder = accounts.at("0x075e72a5eDf65F0A5f44699c7654C1a76941Ddc8", force=True)
#         # ugly hack to simulate order fulfill by DAI
#         # invalidateOrder can be called only by order owner and sets filledAmount[orderUid] = -1
#         # so the Seller contract assumes that order is filled
#         cow_settlement.invalidateOrder(orderUid, {"from": seller_account})
#         # simulating DAI transfer
#         dai_token.transfer(seller_dev.address, buy_amount, {"from": dai_holder})
#         # simulate WETH transfer
#         weth_token.transfer(dai_holder.address, sell_amount, {"from": seller_account})

#     return run


@pytest.fixture
def settled_order(accounts, seller, beneficiary, sell_amount, make_order_sell_weth_for_dai, simulate_seller_refill, weth_token):
    valid_to = chain.time() + 3600
    fee_amount = sell_amount * 0.001
    # simulate good exchange rate
    buy_amount = seller.getChainlinkReversePrice() * (sell_amount - fee_amount)

    order = make_order_sell_weth_for_dai(sell_amount=sell_amount, buy_amount=buy_amount, fee_amount=fee_amount, receiver=beneficiary, valid_to=valid_to)
    orderUid = seller.getOrderUid(order)

    simulate_seller_refill(sell_amount)
    tx = seller.settleOrder(order, orderUid, {"from": accounts[0]})
    return (order, orderUid, tx)


def test_deploy_params(registry, seller, beneficiary, deployRegistryConstructorArgs, deployConstructorArgs):
    regArgs = deployRegistryConstructorArgs(receiver=beneficiary)
    args = deployConstructorArgs(max_slippage=MAX_SLIPPAGE)
    check_deployed(registry=registry, seller=seller, registryConstructorArgs=regArgs, constructorArgs=args)


def test_initialize(accounts, registry, seller):
    dummyAddress = "0x0000000000000000000000000000000000000001"
    impl = OTCSeller.at(registry.implementation())
    # try initialize impl
    with reverts("Only registry can call"):
        impl.initialize(dummyAddress, dummyAddress, dummyAddress, 111, {"from": accounts[0]})
    # retry initialize
    with reverts("Initializable: contract is already initialized"):
        seller.initialize(dummyAddress, dummyAddress, dummyAddress, 111, {"from": accounts[0]})


def test_retry_deploy_same_tokens(accounts, registry, deployConstructorArgs):
    args = deployConstructorArgs(max_slippage=MAX_SLIPPAGE)
    with reverts("Seller exists"):
        registry.createSeller(args.sellTokenAddress, args.buyTokenAddress, args.chainLinkPriceFeedAddress, args.maxSlippage, {"from": accounts[0]})

    # swap tokens
    with reverts("Seller exists"):
        registry.createSeller(args.buyTokenAddress, args.sellTokenAddress, args.chainLinkPriceFeedAddress, args.maxSlippage, {"from": accounts[0]})


def test_get_chainlink_price(seller):
    chainlink_price = seller.getChainlinkDirectPrice()
    assert chainlink_price > 0
    chainlink_price = seller.getChainlinkReversePrice()
    assert chainlink_price > 0


def test_settle_order(seller, sell_amount, settled_order, weth_token, dai_token, cow_settlement):
    (_, orderUid, tx) = settled_order
    assert "OrderSettled" in tx.events
    assert tx.events["OrderSettled"]["orderUid"] == orderUid
    assert "PreSignature" in tx.events
    assert tx.events["PreSignature"]["orderUid"] == orderUid
    assert tx.events["PreSignature"]["signed"] == True

    assert weth_token.allowance(seller.address, cowswap_vault_relayer) >= sell_amount
    assert cow_settlement.preSignature(orderUid) == PRE_SIGNED


def test_cancel_order(accounts, seller, beneficiary, settled_order, cow_settlement):
    (_, orderUid, tx) = settled_order

    with reverts():
        seller.cancelOrder(orderUid, {"from": accounts[0]})
    tx = seller.cancelOrder(orderUid, {"from": beneficiary})

    assert "OrderCanceled" in tx.events
    assert tx.events["OrderCanceled"]["orderUid"] == orderUid
    assert "PreSignature" in tx.events
    assert tx.events["PreSignature"]["orderUid"] == orderUid
    assert tx.events["PreSignature"]["signed"] == False

    assert cow_settlement.preSignature(orderUid) == 0
