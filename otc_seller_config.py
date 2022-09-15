# NOTE: SELL_TOKEN and BUY_TOKEN mast be set in order according ChainLink price feed
# i.e., in the case of selling ETH for DAI, the sellToken must be set to DAI,
# as the ChainLink price feed returns the ETH amount for 1 DAI
# DAI
SELL_TOKEN="0x6B175474E89094C44Da98b954EedeAC495271d0F"
# WETH
BUY_TOKEN="0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"
# ChainLink price feed DAI-ETH
PRICE_FEED="0x773616E4d11A78F511299002da57A0a94577F1f4"
# Lido Agent
BENEFICIARY="0x3e40D73EB977Dc6a537aF587D48316feE66E9C8c"
# initial max slippage, value in BPS
MAX_SLIPPAGE = 200 # 2%
