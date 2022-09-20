import sys
import pytest
from dotmap import DotMap
from brownie import chain, Wei, web3
import utils.log as log
from scripts.deploy import deploy, make_registry_constructor_args, start_dao_vote_transfer_eth_for_sell, make_order, make_initialize_args
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
    chainlink_dai_eth,
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


@pytest.fixture(scope="module", autouse=True)
def app_data():
    return web3.keccak(text="LIDO 4ever!").hex()  # required field, do not change =)
    # return "0x0000000000000000000000000000000000000000000000000000000000000000"


@pytest.fixture(scope="module")
def beneficiary(accounts):
    return accounts[1]


@pytest.fixture(scope="module")
def deployRegistryConstructorArgs():
    def run(receiver):
        # NOTE: sellToken and buyToken mast be set in order according chainlink price feed
        # i.e., in the case of selling ETH for DAI, the sellToken must be set to DAI,
        # as the chainlink price feed returns the ETH amount for 1DAI
        return make_registry_constructor_args(
            weth_token=weth_token_address,
            dao_vault=lido_dao_agent_address,
            receiver=receiver,
        )

    return run


@pytest.fixture(scope="module")
def createSellerInitializeArgs():
    def run(max_margin):
        # NOTE: sellToken and buyToken mast be set in order according chainlink price feed
        # i.e., in the case of selling ETH for DAI, the sellToken must be set to DAI,
        # as the chainlink price feed returns the ETH amount for 1DAI
        return make_initialize_args(
            sell_toke=dai_token_address, buy_token=weth_token_address, price_feed=chainlink_dai_eth, max_margin=max_margin, const_price=0
        )

    return run


@pytest.fixture(scope="module")
def deploy_seller_eth_for_dai(accounts, deployRegistryConstructorArgs, createSellerInitializeArgs):
    def run(receiver, max_margin):
        registryConstructorArgs = deployRegistryConstructorArgs(receiver)
        sellerInitializeArgs = createSellerInitializeArgs(max_margin)
        return deploy({"from": accounts[0]}, registryConstructorArgs, sellerInitializeArgs)

    return run


@pytest.fixture(scope="module")
def make_order_sell_weth_for_dai(app_data):
    def run(sell_amount, buy_amount, fee_amount, receiver, valid_to):
        return make_order(
            sell_token=weth_token_address,
            buy_token=dai_token_address,
            receiver=receiver,
            sell_amount=sell_amount,
            buy_amount=buy_amount,
            valid_to=valid_to,
            app_data=app_data,
            fee_amount=fee_amount,
            partiallyFillable=False,
        )

    return run


@pytest.fixture(scope="module")
def transfer_eth_for_sell_and_pass_dao_vote(ldo_holder, weth_token, helpers):
    def run(seller, sell_amount):
        vote_id = start_dao_vote_transfer_eth_for_sell({"from": ldo_holder}, seller_address=seller.address, sell_amount=sell_amount)
        helpers.pass_and_exec_dao_vote(vote_id)

        assert weth_token.balanceOf(seller.address) >= sell_amount
        return

    return run
