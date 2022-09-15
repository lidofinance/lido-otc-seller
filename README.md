# Lido OTC seller

The OTC Seller is used to exchange one asset from the [DAO Treasury](https://mainnet.lido.fi/#/lido-dao/0x3e40d73eb977dc6a537af587d48316fee66e9c8c/) to another asset at market spot price. The contract implements this type of exchange through the [CowSwap](https://cow.fi/) platform.

## Description

The contract is non-upgradable, and its params supposed to be set upon the construction stage:

- ERC-20 trading pair (or native ether)
- Owner (beneficiary)
- ChainLink price feed
- Spot price margin

Thus, every deployed instance is devoted to represent the single trading scenario flow (e.g. selling LDO to DAI on behalf of Lido DAO Treasury).

The contract allows to have several exchange orders at the same time.

> *NB:* Due to the CowSwap exchange logic, it is necessary to place an order via CowSwap API with an additional toolkit before before or at the moment of order settle.

## Setup

```shell
poetry shell
poetry install

export WEB3_INFURA_PROJECT_ID=<your infura project id>
export ETHERSCAN_TOKEN=<your etherscan api key>
```

## Configuration

The seller parameters are set in [`otc_seller_config.py`]. The following parameters are can be set:

- `SELL_TOKEN` primary token address to exchange.
- `BUY_TOKEN` secondary token address to exchange for.
- `PRICE_FEED` ChainLink price feed address for tokens pair above.
- `BENEFICIARY` Beneficiary address. This address will be recipient of all filled exchange orders. Also it has rights to cancel non filled yet orders.
- `MAX_SLIPPAGE` max allowed slippage from ChainLink price feed on order settle moment.

Example content of `otc_seller_config.py`:

```py
# DAI
SELL_TOKEN=0x6B175474E89094C44Da98b954EedeAC495271d0F
# WETH
BUY_TOKEN=0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2
# ChainLink price feed DAI-ETH
PRICE_FEED=0x773616E4d11A78F511299002da57A0a94577F1f4
# Lido Agent
BENEFICIARY=0x3e40D73EB977Dc6a537aF587D48316feE66E9C8c
# initial max slippage, value in BPS
MAX_SLIPPAGE = 200 # 2%
```

## Run tests

It' better to run local mainnet fork node in separate terminal window.

```shell
brownie console --network mainnet-fork
```

Then run all tests

```shell
brownie test -s --disable-warnings
```

## Deployment

Get sure your account is imported to Brownie: `brownie accounts list`.

Make sure you have exported or set id directly:

```yaml
NETWORK=mainnet # target network alias
DEPLOYER=deployer # deployer account alias
```

Run deploy script and follow the wizard:

```shell
NETWORK=mainnet DEPLOYER=deployer brownie run main
```

After script finishes, all deployed metadata will be saved to file `./deployed-{NETWORK}.json`, i.e. `deployed-mainnet.json`.

Deploy script is stateful, so it safe to start several times. To deploy from scratch, simply delete the `./deployed-{NETWORK}.json` before running it.
