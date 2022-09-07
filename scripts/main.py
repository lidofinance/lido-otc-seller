from brownie import network, accounts, Setup, OTCSeller, OssifiableProxy
import json
from utils.deployed_state import read_or_update_state
from utils.env import get_env
import utils.log as log
from scripts.deploy import deploy, finalize, get_setup_state

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

    log.info("NETWORK", NETWORK)
    log.info("DEPLOYER", deployer.address)
    # log.info("TOKEN", TOKEN)
    # log.info("BRIDGE", BRIDGE)
    # log.info("RECIPIENT_CHAIN", RECIPIENT_CHAIN)
    # log.info("RECIPIENT", RECIPIENT)
    # log.info("ARBITER_FEE", ARBITER_FEE)

    proceed = log.prompt_yes_no("Proceed?")

    if not proceed:
        log.error("Script stopped!")
        return

    log.brief(f"Deploying OTCSeller via factory...")
    (setup, seller) = deploy({"from": deployer}, deployer=deployer)

    setupState = get_setup_state(setup)

    if setupState.lastSetupStatus == 'Deployed':
        log.info("Setup not finalized yet.")
        proceed = log.prompt_yes_no("Continue with finalization?")
        if proceed:
            finalize({"from": deployer}, setup)

    if network.show_active() == 'mainnet':
        proceed = log.prompt_yes_no("(Re)Try to publish source codes?")
        if proceed:
            Setup.publish_source(setup)
            impl = OTCSeller.at(setupState.otcSellerImplAddress)
            OTCSeller.publish_source(impl)
            proxy = OssifiableProxy.at(setupState.otcSellerAddress)
            OssifiableProxy.publish_source(proxy)

            log.okay("Contract sources published!")
    else:
        log.info(f"The current network '{network.show_active()}' is not 'mainnet'. Source publication skipped")

    log.brief("All deployed metadata saved to", f"./deployed-{network.show_active()}.json")
