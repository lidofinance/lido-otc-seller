# Lido token seller

[TBD]

## Setup

```shell
poetry shell
poetry install

export WEB3_INFURA_PROJECT_ID=<your infura project id>
export ETHERSCAN_TOKEN=<your etherscan api key>
```

## Run tests

It' better to run local mainnet fork node in separate terminal window.

```shell
brownie console --network mainnet-fork
```

Then run all tests

```shell
brownie test -s 
```

## Deployment

Get sure your account is imported to Brownie: `brownie accounts list`.

...TBD...
