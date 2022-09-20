from brownie import network, accounts, OTCSeller, OTCRegistry
from utils.env import get_env
import utils.log as log
from scripts.deploy import check_deployed, deploy, make_initialize_args, make_registry_constructor_args
from utils.config import weth_token_address, lido_dao_agent_address, dai_token_address, chainlink_dai_eth
from otc_seller_config import SELL_TOKEN, BUY_TOKEN,PRICE_FEED, BENEFICIARY,  MAX_MARGIN

# environment
WEB3_INFURA_PROJECT_ID = get_env("WEB3_INFURA_PROJECT_ID")
ETHERSCAN_TOKEN = get_env("ETHERSCAN_TOKEN")

# deploy parameters
DEPLOYER = get_env("DEPLOYER")
NETWORK = get_env("NETWORK")


def main():
    log.info("Checking environment variables...")

    if not WEB3_INFURA_PROJECT_ID:
        log.error("`WEB3_INFURA_PROJECT_ID` not found!")
        return

    if not ETHERSCAN_TOKEN:
        log.error("`ETHERSCAN_TOKEN` not found!")
        return

    log.okay("Environment variables - Ok")

    log.info("Checking deploy parameters...")

    if not NETWORK:
        log.error("`NETWORK` not found!")
        return

    if network.show_active() != NETWORK:
        log.error(f"Wrong network! Expected `{NETWORK}` but got", network.show_active())
        return

    if not DEPLOYER:
        log.error("`DEPLOYER` not found!")
        return

    try:
        deployer = accounts.load(DEPLOYER)
    except FileNotFoundError:
        log.error(f"Local account with id `{DEPLOYER}` not found!")
        return

    log.okay("Deploy parameters - Ok")

    log.note("NETWORK", NETWORK)
    log.note("DEPLOYER", deployer.address)

    regArgs = make_registry_constructor_args(
        weth_token=weth_token_address, dao_vault=lido_dao_agent_address, receiver=BENEFICIARY
    )

    log.info("registryConstructorArgs:")
    for k, v in regArgs.items():
        log.note(k, v)

    args = make_initialize_args(
        sell_toke=SELL_TOKEN, buy_token=BUY_TOKEN, price_feed=PRICE_FEED, max_margin=MAX_MARGIN, const_price=0
    )

    log.info("sellerInitializeArgs:")
    for k, v in args.items():
        log.note(k, v)

    proceed = log.prompt_yes_no("Proceed?")

    if not proceed:
        log.error("Script stopped!")
        return

    log.note(f"Deploying OTCSeller (ETH-DAI) via factory...")
    # args.beneficiaryAddress = deployer.address
    (registry, seller) = deploy(tx_params={"from": deployer}, registryConstructorArgs=regArgs, sellerInitializeArgs=args)

    log.info("Checking deployed OTCSeller...")
    check_deployed(registry=registry, seller=seller, registryConstructorArgs=regArgs, sellerInitializeArgs=args)
    log.okay("OTCSeller check pass")

    if network.show_active() == "mainnet":
        proceed = log.prompt_yes_no("(Re)Try to publish source codes?")
        if proceed:
            OTCRegistry.publish_source(registry)
            OTCSeller.publish_source(registry.implementation())
            log.okay("Contract source published!")
    else:
        log.info(f"The current network '{network.show_active()}' is not 'mainnet'. Source publication skipped")

    log.note("All deployed metadata saved to", f"./deployed-{network.show_active()}.json")
