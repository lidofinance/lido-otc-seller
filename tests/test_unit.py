import pytest
from brownie import chain, reverts, Wei, OTCSeller
from scripts.deploy import check_deployed_factory, check_deployed_seller, make_order

from utils.config import lido_dao_agent_address, cowswap_vault_relayer, PRE_SIGNED
from otc_seller_config import MAX_MARGIN

SELL_AMOUNT = Wei("100 ether")


@pytest.fixture
def sell_amount():
    return SELL_AMOUNT


@pytest.fixture
def factory_and_seller(beneficiary, deploy_seller_eth_for_dai):
    return deploy_seller_eth_for_dai(receiver=beneficiary, max_margin=MAX_MARGIN)


@pytest.fixture
def seller(factory_and_seller):
    (_, seller) = factory_and_seller
    return seller


@pytest.fixture
def factory(factory_and_seller):
    (factory, _) = factory_and_seller
    return factory


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
def signed_order(accounts, seller, beneficiary, sell_amount, make_order_sell_weth_for_dai, simulate_seller_refill, weth_token):
    valid_to = chain.time() + 3600
    fee_amount = sell_amount * 0.001
    # simulate good exchange rate
    (chainlink_price, _) = seller.priceAndMaxMargin()
    buy_amount = chainlink_price * (sell_amount - fee_amount)

    order = make_order_sell_weth_for_dai(sell_amount=sell_amount, buy_amount=buy_amount, fee_amount=fee_amount, receiver=beneficiary, valid_to=valid_to)
    orderUid = seller.getOrderUid(order)

    simulate_seller_refill(sell_amount)
    tx = seller.signOrder(order, orderUid, {"from": accounts[0]})
    return (order, orderUid, tx)


def test_deploy_params(factory, seller, beneficiary, deployFactoryConstructorArgs, createSellerInitializeArgs):
    regArgs = deployFactoryConstructorArgs()
    args = createSellerInitializeArgs(receiver=beneficiary, max_margin=MAX_MARGIN)
    check_deployed_factory(factory=factory, factoryConstructorArgs=regArgs)
    check_deployed_seller(factory=factory, seller=seller, sellerInitializeArgs=args)


def test_initialize(accounts, factory, seller):
    dummyAddress = "0x0000000000000000000000000000000000000001"
    impl = OTCSeller.at(factory.implementation())
    # try initialize impl
    with reverts("Only factory can call"):
        impl.initialize(dummyAddress, dummyAddress, dummyAddress, dummyAddress, 1, 1, {"from": accounts[0]})
    # retry initialize
    with reverts("Initializable: contract is already initialized"):
        seller.initialize(dummyAddress, dummyAddress, dummyAddress, dummyAddress, 1, 1, {"from": accounts[0]})


def test_retry_deploy_same_tokens(accounts, factory, beneficiary, createSellerInitializeArgs):
    args = createSellerInitializeArgs(receiver=beneficiary, max_margin=MAX_MARGIN)
    with reverts("Seller exists"):
        factory.createSeller(
            args.beneficiaryAddress,
            args.sellTokenAddress,
            args.buyTokenAddress,
            args.chainLinkPriceFeedAddress,
            args.maxMargin,
            args.constantPrice,
            {"from": accounts[0]},
        )

    # swap tokens
    with reverts("Seller exists"):
        factory.createSeller(
            args.beneficiaryAddress,
            args.buyTokenAddress,
            args.sellTokenAddress,
            args.chainLinkPriceFeedAddress,
            args.maxMargin,
            args.constantPrice,
            {"from": accounts[0]},
        )


def test_get_chainlink_price_and_max_margin(seller):
    (chainlink_price, max_margin) = seller.priceAndMaxMargin()
    (chainlink_reverse_price, max_margin) = seller.reversePriceAndMaxMargin()
    print(chainlink_price, chainlink_reverse_price)
    assert chainlink_price > 0
    assert max_margin == MAX_MARGIN


def test_check_wrong_order(factory, seller, sell_amount, beneficiary, weth_token, dai_token, app_data):

    dummyAddress = "0x0000000000000000000000000000000000000001"

    valid_to = chain.time() + 3600
    fee_amount = sell_amount * 0.05  # 5%
    # simulate good exchange rate
    (chainlink_price, _) = seller.priceAndMaxMargin()
    if seller.tokenA() == weth_token:
        buy_amount = chainlink_price * (sell_amount - fee_amount) / 10**18
    else:
        buy_amount = (sell_amount - fee_amount) * 10**18 / chainlink_price

    # wrong sell_token
    order = make_order(
        sell_token=dummyAddress,  # weth_token,
        buy_token=dai_token,
        receiver=beneficiary,
        sell_amount=sell_amount,
        buy_amount=buy_amount,
        valid_to=valid_to,
        app_data=app_data,
        fee_amount=fee_amount,
        partiallyFillable=False,
    )
    orderUid = seller.getOrderUid(order)
    (checked, result) = seller.checkOrder(order, orderUid)
    assert checked == False and result == "Unsupported tokens pair", result

    # wrong buy_token
    order = make_order(
        sell_token=weth_token,
        buy_token=dummyAddress,
        receiver=beneficiary,
        sell_amount=sell_amount,
        buy_amount=buy_amount,
        valid_to=valid_to,
        app_data=app_data,
        fee_amount=fee_amount,
        partiallyFillable=False,
    )
    orderUid = seller.getOrderUid(order)
    (checked, result) = seller.checkOrder(order, orderUid)
    assert checked == False and result == "Unsupported tokens pair", result

    # wrong receiver
    order = make_order(
        sell_token=weth_token,
        buy_token=dai_token,
        receiver=dummyAddress,
        sell_amount=sell_amount,
        buy_amount=buy_amount,
        valid_to=valid_to,
        app_data=app_data,
        fee_amount=fee_amount,
        partiallyFillable=False,
    )
    orderUid = seller.getOrderUid(order)
    (checked, result) = seller.checkOrder(order, orderUid)
    assert checked == False and result == "Wrong receiver", result

    # wrong validTo
    order = make_order(
        sell_token=weth_token,
        buy_token=dai_token,
        receiver=beneficiary,
        sell_amount=sell_amount,
        buy_amount=buy_amount,
        valid_to=0,
        app_data=app_data,
        fee_amount=fee_amount,
        partiallyFillable=False,
    )
    orderUid = seller.getOrderUid(order)
    (checked, result) = seller.checkOrder(order, orderUid)
    assert checked == False and result == "validTo in the past", result

    # wrong orderUid (reuse previous orderUid with new order data)
    order = make_order(
        sell_token=weth_token,
        buy_token=dai_token,
        receiver=beneficiary,
        sell_amount=sell_amount,
        buy_amount=buy_amount,
        valid_to=valid_to,
        app_data=app_data,
        fee_amount=sell_amount * 0.15,  # 15%,
        partiallyFillable=False,
    )
    (checked, result) = seller.checkOrder(order, orderUid)
    assert checked == False and result == "orderUid mismatch", result
    orderUid = seller.getOrderUid(order)
    (checked, result) = seller.checkOrder(order, orderUid)
    assert checked == False and result == "Order fee to high", result

    # wrong buyAmount
    order = make_order(
        sell_token=weth_token,
        buy_token=dai_token,
        receiver=beneficiary,
        sell_amount=sell_amount,
        buy_amount=buy_amount * 0.9,  # simulate chainlink higher price
        valid_to=valid_to,
        app_data=app_data,
        fee_amount=fee_amount,
        partiallyFillable=False,
    )
    orderUid = seller.getOrderUid(order)
    (checked, result) = seller.checkOrder(order, orderUid)
    assert checked == False and result == "buyAmount too low", result


def test_sign_order(seller, sell_amount, signed_order, weth_token, dai_token, cow_settlement):
    (_, orderUid, tx) = signed_order
    assert "OrderSigned" in tx.events
    assert tx.events["OrderSigned"]["orderUid"] == orderUid
    assert "PreSignature" in tx.events
    assert tx.events["PreSignature"]["orderUid"] == orderUid
    assert tx.events["PreSignature"]["signed"] == True

    assert weth_token.allowance(seller.address, cowswap_vault_relayer) >= sell_amount
    assert cow_settlement.preSignature(orderUid) == PRE_SIGNED


def test_cancel_order(accounts, seller, beneficiary, signed_order, cow_settlement):
    (_, orderUid, tx) = signed_order

    with reverts():
        seller.cancelOrder(orderUid, {"from": accounts[0]})
    tx = seller.cancelOrder(orderUid, {"from": beneficiary})

    assert "OrderCanceled" in tx.events
    assert tx.events["OrderCanceled"]["orderUid"] == orderUid
    assert "PreSignature" in tx.events
    assert tx.events["PreSignature"]["orderUid"] == orderUid
    assert tx.events["PreSignature"]["signed"] == False

    assert cow_settlement.preSignature(orderUid) == 0
