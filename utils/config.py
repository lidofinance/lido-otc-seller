import os
import sys
from brownie import network, accounts, web3


# eth_token_address ='0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE'
eth_token_address = "0x0000000000000000000000000000000000000000"
weth_token_address = "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"
ldo_token_address = "0x5A98FcBEA516Cf06857215779Fd812CA3beF1B32"
lido_dao_acl_address = "0x9895F0F17cc1d1891b6f18ee0b483B6f221b37Bb"
lido_dao_agent_address = "0x3e40D73EB977Dc6a537aF587D48316feE66E9C8c"
lido_dao_finance_address = "0xB9E5CBB9CA5b0d659238807E84D0176930753d86"
lido_dao_voting_address = "0x2e59A20f205bB85a89C53f1936454680651E618e"
lido_dao_token_manager_address = "0xf73a1260d222f447210581DDf212D915c09a3249"
steth_token_address = "0xae7ab96520DE3A18E5e111B5EaAb095312D7fE84"
dai_token_address = "0x6B175474E89094C44Da98b954EedeAC495271d0F"
usdc_token_address = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
usdt_token_address = "0xdAC17F958D2ee523a2206206994597C13D831ec7"

chainlink_dai_eth = "0x773616E4d11A78F511299002da57A0a94577F1f4"
chainlink_usdt_eth = "0xEe9F2375b4bdF6387aa8265dD4FB8F16512A1d46"
chainlink_usdc_eth = "0x986b5E1e1755e3C2440e960477f25201B0a8bbD4"
chainlink_ldo_eth = "0x4e844125952D32AcdF339BE976c98E22F6F318dB"
chainlink_steth_eth = "0x86392dC19c0b719886221c78AB11eb8Cf5c52812"

cowswap_vault_relayer = "0xC92E8bdf79f0507f65a392b0ab4667716BFE0110"
cowswap_settlement = "0x9008D19f58AAbD9eD0D60971565AA8510560ab41"

curve_smart_router = "0xfA9a30350048B2BF66865ee20363067c66f67e58"
curve_synth_swap = "0x58A3c68e2D3aAf316239c003779F71aCb870Ee47"


DEFAULT_ADMIN_ROLE = "0x0000000000000000000000000000000000000000000000000000000000000000"
ORDER_SETTLE_ROLE = "0x8c00e39d0128d60dc88f0a55b6130751360a9124c2aa044096f703f81094c668"
OPERATOR_ROLE = "0x97667070c54ef182b0f5858b034beac1b6f3089aa2d3188bb1e8929f4fa9b929"

PRE_SIGNED = web3.keccak(text="GPv2Signing.Scheme.PreSign").hex() 

 # together these accounts hold 15% of LDO total supply
ldo_vote_executors_for_tests = [
    "0x3e40d73eb977dc6a537af587d48316fee66e9c8c",
    "0xb8d83908aab38a159f3da47a59d84db8e1838712",
    "0xa2dfc431297aee387c05beef507e5335e684fbcd",
]


def get_is_live():
    return network.show_active() != "development"


def get_deployer_account(is_live):
    if is_live and "DEPLOYER" not in os.environ:
        raise EnvironmentError("Please set DEPLOYER env variable to the deployer account name")

    return (
        accounts.load(os.environ["DEPLOYER"]) if is_live else accounts.at(ldo_vote_executors_for_tests[0], force=True)
    )


def prompt_bool():
    choice = input().lower()
    if choice in {"yes", "y"}:
        return True
    elif choice in {"no", "n"}:
        return False
    else:
        sys.stdout.write("Please respond with 'yes' or 'no'")
