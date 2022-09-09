import requests

KIND_SELL = "f3b277728b3fee749481eb3e0b3b48980dbbab78658fc419025cb16eee346775"
BALANCE_ERC20 = "5a28e9363bb942b639270062aa6bb295f434bcdfc42c97267bf003f272060dc9"


def api_get_sell_fee(sell_token, buy_token, sell_amount, network="mainnet"):
    fee_url = f"https://api.cow.fi/{network}/api/v1/feeAndQuote/sell"
    get_params = {"sellToken": sell_token, "buyToken": buy_token, "sellAmountBeforeFee": sell_amount}
    r = requests.get(fee_url, params=get_params)
    assert r.ok and r.status_code == 200
    fee_amount = int(r.json()["fee"]["amount"])
    buy_amount_after_fee = int(r.json()["buyAmountAfterFee"])
    assert fee_amount > 0
    assert buy_amount_after_fee > 0
    return (fee_amount, buy_amount_after_fee)


def api_get_quote(sell_token, buy_token, sell_amount, valid_to, sender, partiallyFillable=False, network="mainnet"):
    quote_url = f"https://api.cow.fi/{network}/api/v1/quote"
    order_payload = {
        "sellToken": sell_token,
        "buyToken": buy_token,
        "sellAmountBeforeFee": int(sell_amount),
        "validTo": valid_to,
        "partiallyFillable": partiallyFillable,
        "from": sender,
        "receiver": "0x0000000000000000000000000000000000000000",
        "appData": "0x0000000000000000000000000000000000000000000000000000000000000000",
        "kind": "sell",
        "sellTokenBalance": "erc20",
        "buyTokenBalance": "erc20",
        "signingScheme": "presign",  # Very important. this tells the api you are going to sign on chain
    }

    r = requests.post(quote_url, json=order_payload)
    assert r.ok and r.status_code == 200
    fee_amount = int(r.json()["fee"]["amount"])
    buy_amount_after_fee = int(r.json()["buyAmountAfterFee"])
    assert fee_amount > 0
    assert buy_amount_after_fee > 0
    return (fee_amount, buy_amount_after_fee)


def api_create_order(
    sell_token,
    buy_token,
    sell_amount,
    buy_amount,
    fee_amount,
    valid_to,
    sender,
    receiver,
    partiallyFillable=False,
    app_data="0x0000000000000000000000000000000000000000000000000000000000000000",
    network="mainnet",
):
    order_url = f"https://api.cow.fi/{network}/api/v1/orders"
    partiallyFillable = False
    order_payload = {
        "sellToken": sell_token,
        "buyToken": buy_token,
        "sellAmount": str(sell_amount),  # sell amount before fee
        "buyAmount": str(buy_amount),  # buy amount after fee
        "validTo": valid_to,
        "appData": app_data,
        "feeAmount": str(fee_amount),
        "kind": "sell",
        "partiallyFillable": partiallyFillable,
        "receiver": receiver,
        "signature": "0x",
        "from": sender,
        "sellTokenBalance": "erc20",
        "buyTokenBalance": "erc20",
        "signingScheme": "presign",  # Very important. this tells the api you are going to sign on chain
    }
    r = requests.post(order_url, json=order_payload)

    assert r.ok and r.status_code == 201
    order_uid = r.json()
    return order_uid
