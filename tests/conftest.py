import sys
import pytest
from brownie import chain, Wei, web3
import utils.log as log
from scripts.deploy import start_dao_vote_sell_eth_for_dai, deploy_non_finalized, deploy_finalized

from utils.cow import KIND_SELL, BALANCE_ERC20, api_get_sell_fee, api_create_order

from utils.config import (
    eth_token_address,
    weth_token_address,
    ldo_token_address,
    lido_dao_acl_address,
    lido_dao_agent_address,
    lido_dao_voting_address,
    lido_dao_token_manager_address,
    dai_token_address,
    ldo_vote_executors_for_tests,
    cowswap_settlement,
)


def pytest_configure(config):
    # import sys
    sys._called_from_test = True


def pytest_unconfigure(config):
    # import sys  # This was missing from the manual
    del sys._called_from_test


@pytest.fixture(scope="function", autouse=True)
def shared_setup(fn_isolation):
    pass


@pytest.fixture(scope="module")
def setup_and_seller_non_finalized(accounts):
    return deploy_non_finalized({"from": accounts[0]}, deployer=accounts[0])


@pytest.fixture(scope="module")
def setup_and_seller_finalized(accounts):
    return deploy_finalized({"from": accounts[0]}, deployer=accounts[0])


@pytest.fixture(scope="module")
def ldo_holder(accounts):
    return accounts.at("0xAD4f7415407B83a081A0Bee22D05A8FDC18B42da", force=True)


@pytest.fixture(scope="module")
def stranger(accounts):
    return accounts[9]


@pytest.fixture(scope="module")
def dai_token(interface):
    return interface.Dai(dai_token_address)


@pytest.fixture(scope="module")
def weth_token(interface):
    return interface.ERC20(weth_token_address)


@pytest.fixture(scope="module")
def dao_acl(interface):
    return interface.ACL(lido_dao_acl_address)


@pytest.fixture(scope="module")
def dao_voting(interface):
    return interface.Voting(lido_dao_voting_address)


@pytest.fixture(scope="module")
def dao_token_manager(interface):
    return interface.TokenManager(lido_dao_token_manager_address)


# Lido DAO Agent app
@pytest.fixture(scope="module")
def dao_agent(interface):
    return interface.Agent(lido_dao_agent_address)


@pytest.fixture(scope="module")
def ldo_token(interface):
    return interface.ERC20(ldo_token_address)


@pytest.fixture(scope="module")
def cow_settlement(interface):
    return interface.Settlement(cowswap_settlement)


class Helpers:
    accounts = None
    eth_banker = None
    # dao_voting = None
    dai_token = None

    @staticmethod
    def fund_with_eth(addr, amount="1000 ether"):
        Helpers.eth_banker.transfer(to=addr, amount=amount)

    @staticmethod
    def fund_with_dai(addr, amount):
        stranger = Helpers.accounts.at("0x075e72a5edf65f0a5f44699c7654c1a76941ddc8", force=True)
        Helpers.dai_token.transfer(addr, amount, {"from": stranger})

    @staticmethod
    def filter_events_from(addr, events):
        return list(filter(lambda evt: evt.address == addr, events))

    @staticmethod
    def assert_single_event_named(evt_name, tx, evt_keys_dict=None):
        receiver_events = Helpers.filter_events_from(tx.receiver, tx.events[evt_name])
        assert len(receiver_events) == 1
        if evt_keys_dict is not None:
            assert dict(receiver_events[0]) == evt_keys_dict
        return receiver_events[0]

    @staticmethod
    def pass_and_exec_dao_vote(vote_id):
        log.info(f"executing vote {vote_id}")

        helper_acct = Helpers.accounts[0]

        for holder_addr in ldo_vote_executors_for_tests:
            log.info(f"voting from {holder_addr}")
            helper_acct.transfer(holder_addr, "0.1 ether")
            account = Helpers.accounts.at(holder_addr, force=True)
            Helpers.dao_voting.vote(vote_id, True, False, {"from": account})

        # wait for the vote to end
        chain.sleep(3 * 60 * 60 * 24)
        chain.mine()

        assert Helpers.dao_voting.canExecute(vote_id)
        Helpers.dao_voting.executeVote(vote_id, {"from": helper_acct})

        log.okay(f"vote {vote_id} executed")


@pytest.fixture(scope="module")
def helpers(accounts, dao_voting, dai_token):
    Helpers.accounts = accounts
    Helpers.eth_banker = accounts.at("0xBE0eB53F46cd790Cd13851d5EFf43D12404d33E8", force=True)
    Helpers.dao_voting = dao_voting
    Helpers.dai_token = dai_token
    return Helpers


@pytest.fixture(scope="module")
def deploy_not_finalized_seller(accounts):
    def deploy(accounts):
        (setup, seller) = deploy_non_finalized({"from": accounts[0]}, deployer=accounts[0])
        return (setup, seller)

    return deploy


@pytest.fixture(scope="module")
def deploy_finalized_seller(accounts):
    def deploy():
        (setup, seller) = deploy_finalized({"from": accounts[0]}, deployer=accounts[0])
        return (setup, seller)

    return deploy


@pytest.fixture(scope="module", autouse=True)
def sell_token():
    return weth_token_address


@pytest.fixture(scope="module", autouse=True)
def buy_token():
    return dai_token_address


@pytest.fixture(scope="module", autouse=True)
def sell_amount():
    return Wei("10000 ether")


@pytest.fixture(scope="module", autouse=True)
def fee_buy_amount(sell_token, buy_token, sell_amount):
    return api_get_sell_fee(sell_token, buy_token, sell_amount, "mainnet")


@pytest.fixture(scope="module", autouse=True)
def buy_amount(fee_buy_amount):
    _, buy_amount = fee_buy_amount
    return buy_amount


@pytest.fixture(scope="module", autouse=True)
def fee_amount(fee_buy_amount):
    fee_amount, _ = fee_buy_amount
    return fee_amount


@pytest.fixture(scope="module", autouse=True)
def appData():
    return web3.keccak(text="LIDO 4ever!").hex()  # required field, do not change =)
    # return "0x0000000000000000000000000000000000000000000000000000000000000000"


@pytest.fixture(scope="module", autouse=True)
def valid_to(dao_voting):
    return chain.time() + dao_voting.voteTime() + 3600  # max voting period + 1h


@pytest.fixture(scope="module", autouse=True)
def partiallyFillable():
    return False


@pytest.fixture(scope="module", autouse=True)
def seller(setup_and_seller_finalized):
    (_, seller) = setup_and_seller_finalized
    return seller


@pytest.fixture(scope="module", autouse=True)
def seller_dev(setup_and_seller_non_finalized):
    (_, seller) = setup_and_seller_non_finalized
    return seller


@pytest.fixture(scope="module")
def order_sell_eth_for_dai(sell_token, buy_token, sell_amount, buy_amount, fee_amount, valid_to, appData, partiallyFillable):
    def make_order(seller):
        order = [
            sell_token,
            buy_token,
            seller.address,
            int(sell_amount),
            int(buy_amount),
            valid_to,
            appData,
            int(fee_amount),
            KIND_SELL,
            partiallyFillable,
            BALANCE_ERC20,
            BALANCE_ERC20,
        ]
        return order

    return make_order


@pytest.fixture(scope="module")
def settle_order_and_pass_dao_vote(ldo_holder, sell_amount, buy_amount, fee_amount, valid_to, appData, partiallyFillable, helpers):
    def run(seller, orderUid, valid_to=valid_to, partiallyFillable=partiallyFillable):
        vote_id = start_dao_vote_sell_eth_for_dai(
            {"from": ldo_holder},
            seller.address,
            sell_amount,
            buy_amount,
            valid_to,
            appData,
            fee_amount,
            partiallyFillable,
            orderUid,
        )
        helpers.pass_and_exec_dao_vote(vote_id)
        return orderUid

    return run
