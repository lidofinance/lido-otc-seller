from dotmap import DotMap
from utils.deployed_state import read_or_update_state
import utils.log as log

try:
    from brownie import Setup, TokenSeller, interface, Wei
except ImportError:
    print("You're probably running inside Brownie console. Please call:")
    print("set_console_globals(interface=interface, PurchaseExecutor=PurchaseExecutor)")


def set_console_globals(**kwargs):
    global Setup
    global TokenSeller
    global interface
    TokenSeller = kwargs["TokenSeller"]
    interface = kwargs["interface"]


from utils.dao import create_vote, encode_settle_order, encode_token_transfer, encode_call_script, encode_agent_execute

from utils.config import (
    eth_token_address,
    weth_token_address,
    dai_token_address,
    lido_dao_agent_address,
    lido_dao_voting_address,
    lido_dao_finance_address,
    lido_dao_token_manager_address,
)

from token_seller_config import SLIPPAGE, TOTAL_ETH_TO_SELL


def propose_sell_eth_for_dai(
    tx_params,
    seller_address,
    sell_amount,
    buy_amount,
    valid_to,
    appData,
    fee_amount,
    partiallyFillable,
    orderUid,
    reference,
):

    agent = interface.Agent(lido_dao_agent_address)
    voting = interface.Voting(lido_dao_voting_address)
    finance = interface.Finance(lido_dao_finance_address)
    token_manager = interface.TokenManager(lido_dao_token_manager_address)
    seller = TokenSeller.at(seller_address)

    (_, settle_call_data) = encode_settle_order(
        sell_token=weth_token_address,  # NOTE: in case of ETH, token address here must be WETH as we will sell wrapped ETH to WETH actually
        buy_token=dai_token_address,
        receiver=seller_address,  # NOTE: receiver is the seller contract itself, see notes for {TokenSeller.sol-checkOrder}
        sell_amount=sell_amount,
        buy_amount=buy_amount,
        valid_to=valid_to,
        appData=appData,
        fee_amount=fee_amount,
        partiallyFillable=partiallyFillable,
        orderUid=orderUid,
        seller=seller,
    )

    evm_script = encode_call_script(
        [
            encode_token_transfer(
                token_address=eth_token_address,  # NOTE: in case of ETH, token address here must be 0x0000000000000000000000000000000000000000
                recipient=seller_address,
                amount=sell_amount,
                reference=reference,
                finance=finance,
            ),
            encode_agent_execute(target=seller_address, call_value=0, call_data=settle_call_data, agent=agent),
        ]
    )
    return create_vote(
        voting=voting,
        token_manager=token_manager,
        vote_desc=f"Sell {Wei(sell_amount).to('ether')} ETH for total {Wei(buy_amount).to('ether')} DAI, Seller contract: {seller.address}, CowSwap orderUid: {orderUid}",
        evm_script=evm_script,
        tx_params=tx_params,
    )


def format_setup_status(status=0):
    statuses = {
        0: "None",
        1: "Deployed",
        2: "Finalized",
    }
    return statuses.get(status, statuses[0])


def get_setup_state(setup):
    [lastSetupStatus, deployerAddress, tokenSellerImplAddress, tokenSellerAddress] = setup.getSetupState()
    # filter "setup" parameter from local vars
    state = DotMap({k: v for (k, v) in locals().items() if k != "setup"})
    state.lastSetupStatus = format_setup_status(state.lastSetupStatus)
    return state


def deploy(tx_params, deployer):
    deployedState = read_or_update_state()

    # setupAddress = deployedState.get("setupAddress") or ""
    if deployedState.setupAddress:
        log.highlight("Setup template already deployed at", deployedState.setupAddress)
        setup = Setup.at(deployedState.setupAddress)
    else:
        log.info("Deploying setup template (and TokenSeller contracts)...")
        setup = Setup.deploy(deployer.address, tx_params)
        log.info("> txHash:", setup.tx.txid)
        log.okay("Setup template deployed at", setup.address)

        # print("setupState", setupState)
        deployedState = read_or_update_state({"setupDeployTx": setup.tx.txid, "setupAddress": setup.address})
    setupState = get_setup_state(setup)
    deployedState = read_or_update_state(setupState)

    log.okay("TokenSeller deployed at", setupState.tokenSellerAddress)
    log.okay("TokenSeller implementation deployed at", setupState.tokenSellerImplAddress)

    log.assert_equals("Setup status", setupState.lastSetupStatus, "Deployed")

    seller = TokenSeller.at(setupState.tokenSellerAddress)
    return (setup, seller)


def finalize(tx_params, setup_address):
    setup = Setup.at(setup_address)
    log.info("Finalizing TokenSeller setup...")
    setupState = get_setup_state(setup)
    log.assert_equals("Tx sender and actual deployer mismatch", tx_params["from"].address, setupState.deployerAddress)

    tx = setup.finalize(tx_params)
    log.info("> txHash:", tx.txid)
    read_or_update_state({"setupFinalizeTx": tx.txid})

    setupState = get_setup_state(setup)
    log.assert_equals("Setup status", setupState.lastSetupStatus, "Finalized")
    read_or_update_state(setupState)
    setup.check()
    log.brief("TokenSeller setup finalized and self-checked!")

    seller = TokenSeller.at(setupState.tokenSellerAddress)
    return (setup, seller)


def deploy_non_finalized(tx_params, deployer):
    (setup, seller) = deploy(tx_params=tx_params, deployer=deployer)
    return (setup, seller)


def deploy_finalized(tx_params, deployer):
    (setup, seller) = deploy_non_finalized(tx_params, deployer)
    finalize(tx_params, setup.address)
    return (setup, seller)


def start_dao_vote_sell_eth_for_dai(
    tx_params, seller_address, sell_amount, buy_amount, valid_to, appData, fee_amount, partiallyFillable, orderUid
):
    (vote_id, _) = propose_sell_eth_for_dai(
        tx_params=tx_params,
        seller_address=seller_address,
        sell_amount=sell_amount,
        buy_amount=buy_amount,
        valid_to=valid_to,
        appData=appData,
        fee_amount=fee_amount,
        partiallyFillable=partiallyFillable,
        orderUid=orderUid,
        reference=f"Transfer ETH to be sold for DAI",
    )
    return vote_id
