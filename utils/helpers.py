import sys
import utils.log as log


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
