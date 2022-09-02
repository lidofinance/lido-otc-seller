from utils.evm_script import encode_call_script, EMPTY_CALLSCRIPT

from utils.cow import KIND_SELL, BALANCE_ERC20


def create_vote(voting, token_manager, vote_desc, evm_script, tx_params):
    new_vote_script = encode_call_script(
        [
            (
                voting.address,
                voting.newVote.encode_input(
                    evm_script if evm_script is not None else EMPTY_CALLSCRIPT, vote_desc, False, False
                ),
            )
        ]
    )
    tx = token_manager.forward(new_vote_script, tx_params)
    vote_id = tx.events["StartVote"]["voteId"]
    return (vote_id, tx)


def encode_token_transfer(token_address, recipient, amount, reference, finance):
    return (finance.address, finance.newImmediatePayment.encode_input(token_address, recipient, amount, reference))


def encode_settle_order(
    sell_token_address,
    buy_token_address,
    receiver_address,
    sell_amount,
    buy_amount,
    valid_to,
    fee_amount,
    orderUid,
    seller,
):
    #  struct Data {
    #     IERC20 sellToken;
    #     IERC20 buyToken;
    #     address receiver;
    #     uint256 sellAmount;
    #     uint256 buyAmount;
    #     uint32 validTo;
    #     bytes32 appData;
    #     uint256 feeAmount;
    #     bytes32 kind;
    #     bool partiallyFillable;
    #     bytes32 sellTokenBalance;
    #     bytes32 buyTokenBalance;
    # }

    partiallyFillable = False
    appData = "0x0000000000000000000000000000000000000000000000000000000000000000"
    return (
        seller.address,
        seller.swapETHForDAI.encode_input(
            [
                sell_token_address,
                buy_token_address,
                receiver_address,
                sell_amount,
                buy_amount,
                valid_to,
                appData,
                fee_amount,
                KIND_SELL,
                partiallyFillable,
                BALANCE_ERC20,
                BALANCE_ERC20,
            ],
            orderUid,
        ),
    )
