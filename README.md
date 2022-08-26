# Lido token seller

[TBD]

## Setup

```shell
poetry shell
poetry install
npm install
export WEB3_INFURA_PROJECT_ID=<your infura project id>
```

## Run tests

```shell
ape test -s --network :mainnet-fork
```


## Deployment

> **NB:** The deployment is done via Ape console because this contract deployment is trivial and because Ape doesn't provide the capability to specify deployer account in a script.

Get sure your account is imported to Ape: `ape accounts list`.

Start Ape console for the target network and provider, e. g.
```bash
ape console --network :mainnet:infura
```

Deploy from the console:

...TBD...
