# FlashLoan Arbitrage Trading Bot

The repository implements a FlashLoan arbitrage bot in python that leverages FlashLoan from DyDx to carry on arbitrage trades between 0x protocol & UniSwap for WETH-DAI trading pair.

This bot was made for a job application and I do not recommend deploying it on Ethereum Mainnet, unless further optimized. Deploying the bot contract might cost you around 50-100 USD, and I am not sure whether you will be able to recover the cost without further optimizations.

Also all contract addresses in the code are for Ethereum mainnet, do not forget to replace them if you are any other network.

I might add more strategies in the future, since right now the arbitrage trade opportunity is only limited to DAI->WETH->DAI from 0x -> UNISWAP only. Although the next logical step would be to add support for WETH->DAI->WETH arbitrage route, I have many more suggestions.

Following are my suggestions for improving the bot:

1. The **run** function loops through every bid & checks for arbitrage opportunity, limiting the performance of the bot. This can be made much better by first finding the exchange rate offered by each bid (i.e rate for WETH-DAI pair), checking the ones that qualify for arbitrage by querying rates on Uniswap, take loan collectively and execute the trade in batch.
2. Leverage Uniswap's Flashswap to trade in opposite direction from UNISWAP -> 0x for WETH-DAI trading pair.
3. Can add support for more trading pairs along with adding support for 1inch to replace Uniswap, since 1inch is a dex aggregator and might offer better prices.
4. Can add support for more exchanges that can offer better rates or might have better arbitrage opportunities. For example, arbitrage opportunities in stable coin pairs (for example, USDC-DAI) will be more profitable between ANY_DEX & Curve (since Curve offers best prices & lower slippage for stables coins) than between ANY_DEX & ANY_DEX_2.

Note - Before running make sure to add configurations to AccountConfig.json file.
