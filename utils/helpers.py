import sys
import utils.log as log
from brownie import Wei


def proceed_or_abort():
    proceed = log.prompt_yes_no("Proceed?")
    if not proceed:
        log.error("Script aborted!")
        sys.exit()
        # return


def is_called_from_test():
    if hasattr(sys, "_called_from_test"):
        # called from within a test run
        return True
    else:
        # called "normally"
        return False


def parseUnit(amount, decimals=18):
    if decimals < 18:
        return Wei(f"{amount} ether") // 10 ** (18 - decimals)
    return Wei(f"{amount} ether")


def formatUnit(amount, decimals=18):
    if decimals < 18:
        corr = 18 - decimals
        return str(Wei(amount * 10 ** (corr)).to("ether"))[:-corr]
    return str(Wei(amount).to("ether"))
