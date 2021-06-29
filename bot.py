from web3 import Web3
import json
import requests
import threading
import time
import signal
import sys

class IntervalCall(object):
    def __init__(self, time_interval, function):
        self.time_interval = time_interval
        self.function = function
        self.timer = None
        self.running = False
        self.next_time = time.time()
        self.start()
    
    def start(self):
        if self.running == False:
            self.next_time += self.time_interval
            self.timer = threading.Timer(self.next_time - time.time(), self.run)
            self.timer.start()
            self.running = True
    
    def run(self):
        self.running = False
        self.start()
        self.function()

    def stop(self):
        self.timer.cancel()
        self.running = False

class Bot():

    def __init__(self):
        # ERC20 token addresses (all addresses are mainnet)
        self.WETH_ADD = Web3.toChecksumAddress("0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2")
        self.DAI_ADD = Web3.toChecksumAddress("0x6b175474e89094c44da98b954eedeac495271d0f")

        # exchange addresses
        self.UNISWAP_V2_FACTORY_ADD = "0x5C69bEe701ef814a2B6a3EDD4B1652CB9cc5aA6f"
        self.ZERO_X_EXCHANGE__PROXY_ADD = "0x61935CbDd02287B511119DDb11Aeb42F1593b7Ef"

        # Bot contract address
        self.BOT_ADD = ""

        self.__load_configs()

        # setups
        self.__setup_node_provider()
        self.__setup_uniswap_pair()
        self.__setup_zero_x_exchange()
        self.__setup_bot()
        self.__setup_account()

        # indicates whether arb trade is in progress or not
        self.running_trade = False

        self.run_count = 0

    def __load_configs(self):
        with open("./AccountConfig.json") as dataFile:
            data = dataFile.read()
            self.configs = json.loads(data)

    def __setup_node_provider(self):
        self.w3 = Web3(Web3.WebsocketProvider(self.configs["INFURA"]["WSS_ENDPOINT"]))
        pass

    def __setup_uniswap_pair(self):
        with open("./abis/IUniswapV2Factory.json") as dataFile:
            data = dataFile.read()
            self.UNISWAP_V2_FACTORY_ABI = json.loads(data)["abi"]
            self.uniswapFactory = self.w3.eth.contract(abi=self.UNISWAP_V2_FACTORY_ABI, address=self.UNISWAP_V2_FACTORY_ADD)

        with open("./abis/IUniswapV2Pair.json") as dataFile:
            data = dataFile.read()
            self.UNISWAP_V2_PAIR_ABI = json.loads(data)["abi"]
            uniWethDaiPairAdd = self.uniswapFactory.functions.getPair(self.WETH_ADD, self.DAI_ADD ).call()
            self.uniWethDaiPair = self.w3.eth.contract(abi=self.UNISWAP_V2_PAIR_ABI, address=uniWethDaiPairAdd)
        
    def __setup_zero_x_exchange(self):
        # ref 0x protocol - https://github.com/0xProject/protocol/blob/development/contracts/zero-ex/contracts/src/features/native_orders/NativeOrdersSettlement.sol
        with open("./abis/ZeroXExchangeProxy.json") as dataFile:
            data = dataFile.read()
            self.ZERO_X_EXCHANGE_PROXY_ABI = json.loads(data)["abi"]
            self.zero_x_exchange_proxy = self.w3.eth.contract(abi=self.ZERO_X_EXCHANGE_PROXY_ABI, address=self.ZERO_X_EXCHANGE__PROXY_ADD)

    def __setup_bot(self):
        with open("./abis/Bot.json") as dataFile:
            data = dataFile.read()
            self.BOT_CONTRACT_ABI = json.loads(data)["abi"]
            self.bot_contract = self.w3.eth.contract(abi=self.BOT_CONTRACT_ABI, address=self.BOT_ADD)

    def __setup_account(self):
        with open("./AccountConfig.json") as dataFile:
            data = dataFile.read()
            self.private_key = self.configs["WALLET"]["PRIVATE_KEY"]
            self.public_address = self.configs["WALLET"]["PUBLIC_ADDRESS"]

    def check_arb(self, zerox_vals, zerox_bid):
        # check uniswap rates for weth-dai
        uni_reserves = self.uniWethDaiPair.functions.getReserves().call()
        uniswap_rate = uni_reserves[0]/uni_reserves[1]

        input_am = zerox_vals["taker_amount"]
        output_am = uniswap_rate * zerox_vals["maker_amount"]

        # calculate trade profitability (Need to account for slippage, since uniswap rate gets worse as orders gets biggers commpared to pool size)
        # estimate gas later
        trade_outcome = output_am - input_am # still haven't taken slippage into account

        if (trade_outcome > 0):
            self.trade(zerox_bid, trade_outcome)
            pass


    def trade(self, zerox_bid, trade_outcome):
        print("Found a arbitrage opportunity - preparing to execute")
        self.running_trade = True
        # zerox fill order ref - https://github.com/0xProject/protocol/blob/development/contracts/zero-ex/contracts/src/features/libs/LibNativeOrder.sol
        zerox_order = (
            Web3.toChecksumAddress(zerox_bid["order"]["makerToken"]),            
            Web3.toChecksumAddress(zerox_bid["order"]["takerToken"]),                                 
            int(zerox_bid["order"]["makerAmount"]),            
            int(zerox_bid["order"]["takerAmount"]),            
            int(zerox_bid["order"]["takerTokenFeeAmount"]),                 
            Web3.toChecksumAddress(zerox_bid["order"]["maker"]),                 
            Web3.toChecksumAddress(zerox_bid["order"]["taker"]),                 
            Web3.toChecksumAddress(zerox_bid["order"]["sender"]),                 
            Web3.toChecksumAddress(zerox_bid["order"]["feeRecipient"]),                 
            zerox_bid["order"]["pool"],                 
            int(zerox_bid["order"]["expiry"]),                 
            int(zerox_bid["order"]["salt"]),                           
        )

        # zerox fill signature ref - https://github.com/0xProject/protocol/blob/development/contracts/zero-ex/contracts/src/features/libs/LibSignature.sol
        zerox_signature = (
            int(zerox_bid["order"]["signature"]["signatureType"]),                           
            int(zerox_bid["order"]["signature"]["v"]),                           
            zerox_bid["order"]["signature"]["r"],                           
            zerox_bid["order"]["signature"]["s"],                           
        )

        # data for zerox trade
        zero_x_data = self.zero_x_exchange_proxy.encodeABI(fn_name="fillLimitOrder", args=[zerox_order, zerox_signature, int(zerox_bid["order"]["takerAmount"])])

        # estimate gas for trade
        gas_price = self.w3.eth.gas_price
        gas_estimate = self.bot_contract.functions.startTrade(int(zerox_bid["order"]["takerAmount"]), int(zerox_bid["order"]["makerAmount"]), zero_x_data).estimateGas()
        total_gas_price = gas_price * gas_estimate

        if (trade_outcome - total_gas_price <= 0):
            self.print_log("GAS price will eat the profit - Aborting trade")
            self.running_trade = False
            return

        # carry on the trade 
        nonce = self.w3.eth.get_transaction_count(self.public_address)
        start_trade_txn = self.bot_contract.functions.startTrade(int(zerox_bid["order"]["takerToken"]), int(zerox_bid["order"]["makerToken"]), zero_x_data).buildTransation({
            "chainId":1,
            "gas":gas_estimate,
            "gasPrice":gas_price,
            "nonce":nonce
        })
        signed_txn = self.w3.eth.account.sign_transaction(start_trade_txn, private_key=self.private_key)
        txn_hash =  w3.eth.send_raw_transaction(signed_txn.rawTransaction)
        
        # wait for confirmation
        web3.eth.wait_for_transaction_receipt(txn_hash)

        self.running_trade = False
        self.print_log("ARB trade was successful")


    def run(self):
        if (self.running_trade == True):
            return

        self.print_log("Starting Bot. Run count - " + str(self.run_count))

        #get orderbook WETH-DAI from zeroX
        req_url = "https://api.0x.org/sra/v4/orderbook?baseToken="+self.DAI_ADD+"&quoteToken="+self.WETH_ADD+"&perPage=1000"
        zerox_response = requests.get(url=req_url)
        zerox_bids = zerox_response.json()["bids"]["records"]
        # asks = zerox_response.json()["asks"]["records"]

        #iterate through each bid record & check arbitrage
        for bid in zerox_bids:
            # pre checks
            if (bid["order"]["takerAmount"] != bid["metaData"]["remainingFillableTakerAmount"]):
                return
            if (bid["order"]["taker"] != "0x0000000000000000000000000000000000000000"):
                return
            
            bid_vals = {
                "taker_symbol":"DAI",
                "taker_amount":float(Web3.fromWei(int(bid["order"]["takerAmount"] ), 'ether')),
                "maker_amount":float(Web3.fromWei(int(bid["order"]["makerAmount"] ), 'ether')),
            }

            self.check_arb(bid_vals, bid)

        self.run_count += 1
        self.print_log("Stopping bot")
    
    def print_log(self, msg):
        print(msg + "\n")

if __name__ == "__main__":
    bot = Bot()
    # check for arbitrage opportunities every 10s 
    timer = IntervalCall(5, bot.run)
