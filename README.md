# Lido OTC seller

The OTC Seller is used to exchange one asset from the [DAO Treasury](https://mainnet.lido.fi/#/lido-dao/0x3e40d73eb977dc6a537af587d48316fee66e9c8c/) to another asset at market spot price within the defined margin. The contract implements this type of exchange through the [CowSwap](https://cow.fi/) platform.

## Description

The `OTCRegistry` and  `OTCSeller` contracts are non-upgradable, and its params supposed to be set upon the construction stage:

- ERC-20 trading pair (or native ether)
- Owner (beneficiary)
- ChainLink price feed
- Spot price margin

The OTCRegistry facilitates the deployments of OTCSeller instances covering different trading scenarios.

> *NB:* Due to the CowSwap exchange logic, it is necessary to place an order via CowSwap API with an additional toolkit before before or at the moment of order settle.

## Setup

```shell
poetry shell
poetry install

export WEB3_INFURA_PROJECT_ID=<your infura project id>
export ETHERSCAN_TOKEN=<your etherscan api key>
```

## Configuration

The default deployment parameters are set in [`otc_seller_config.py`]. The following parameters are can be set:

- `BENEFICIARY` Beneficiary address. This address will be recipient of all filled exchange orders. Also it has rights to cancel non filled yet orders.
- `MAX_MARGIN` max allowed spot price margin from ChainLink price feed on order settle moment.
- `CONST_PRICE` constant token conversion price. It can be set when no price feed for pair exists, so in this case PRICE_FEED should be set to zero address. Otherwise CONST_PRICE should be set to zero.

Example content of `otc_seller_config.py`:

```py
# Lido Agent
BENEFICIARY=0x3e40D73EB977Dc6a537aF587D48316feE66E9C8c
# initial max spot price margin, value in BPS
MAX_MARGIN = 200 # 2%
# constant price not used
CONST_PRICE = 0
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

Make sure your account is imported to Brownie: `brownie accounts list`.

Make sure you have exported or set id directly:

```yaml
DEPLOYER=deployer # deployer account alias
```

To deploy OTCRegistry run deploy script and follow the wizard:

```shell
DEPLOYER=deployer brownie run --network mainnet main deployRegistry [<beneficiaryAddress = BENEFICIARY>]
```

where:

- `<beneficiaryAddress>` - address of beneficiary, is optional, its value will be taken from the configuration file by default (see [Configuration](#configuration) section).

At the deploy moment `deployer` account becomes the `OTCRegistry` owner. The owner can be changed by calling the `transferOwnership` method (e.g., to transfer ownership to the DAO agent)

After script finishes, all deployed metadata will be saved to file `./deployed-{NETWORK}.json`, i.e. `deployed-mainnet.json`.

Deploy script is stateful, so it safe to start several times. To deploy from scratch, simply delete the `./deployed-{NETWORK}.json` before running it.

### Deploying additional seller for other tokens

`OTCRegistry` allows to have multiple sellers for different token pairs. To deploy additional seller run the next command and follow the wizard:

```shell
DEPLOYER=deployer brownie run --network mainnet main deploySeller <sellTokenAddress> <buyTokenAddress> <priceFeedAddress> [<maxMargin = MAX_MARGIN>] [<constantPrice = CONST_PRICE>]
```

where:

- `<sellTokenAddress>` primary token address to exchange.
- `<buyTokenAddress>` secondary token address to exchange for.
- `<priceFeedAddress>` ChainLink price feed address for tokens pair above.
- `<maxMargin>` and  `<constantPrice>` are optional, their value will be taken from the configuration file by default (see [Configuration](#configuration) section).

> *NB:* `<sellTokenAddress>` and `<buyTokenAddress>` must be set in order according ChainLink price feed, i.e. in the case of selling ETH for DAI, the sellToken must be set to DAI, as the ChainLink price feed returns the ETH amount for 1 DAI.

Example for ETH-for-DAI seller:

```shell
# SELL_TOKEN and BUY_TOKEN must be set to order according ChainLink price feed
# i.e., in the case of selling ETH for DAI, the sellToken must be set to DAI,
# as the ChainLink price feed returns the ETH amount for 1 DAI
# DAI
export SELL_TOKEN = "0x6B175474E89094C44Da98b954EedeAC495271d0F"
# WETH
export BUY_TOKEN = "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"
# ChainLink price feed DAI-ETH
export PRICE_FEED = "0x773616E4d11A78F511299002da57A0a94577F1f4"

DEPLOYER=deployer brownie run --network mainnet main deploySeller $SELL_TOKEN $BUY_TOKEN $PRICE_FEED
```

At the deploy moment `deployer` account must be an `OTCRegistry` owner. In case when ownership is transferred to DAO Agent, transaction should be executed during the Voting execution phase (on behalf DAO Agent).

After script finishes, all deployed metadata will be saved to file `./deployed-{NETWORK}.json`, i.e. `deployed-mainnet.json`.

## Usage

When `OTCSeller` for desired token pair is deployed and it balance is topped up with some amount of *sell token*, anyone can create and settle orders using CowSwap API and contract public methods.

The following command automates the order creation process and allows  to control all the parameters to avoid mistakes.

```shell
EXECUTOR=deployer brownie run --network mainnet main settleOrder <sellTokenAddress> <buyTokenAddress> <sellAmount> [<validPeriod> = 3600]
```

where:

- `EXECUTOR` - transaction executor Brownie account alias
- `sellTokenAddress` token address to exchange.
- `buyTokenAddress` secondary token address to exchange for.
- `sellAmount` - desired amount of *sell token* to sell, should be less or equal the seller contract balance. Amount must be set to *human readable* format, not the in Weis, i.e. `10.5 ETH` is written as `10.5`, script will transform amount automatically according the token decimals.
- `validPeriod` - duration in seconds from the current moment during which the order will be valid and available for execution on CowSwap. By default = 3600 (1hour).
