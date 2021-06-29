pragma solidity >=0.6.2;
pragma experimental ABIEncoderV2;

import {IUniswapV2Router02} from './IUniswapV2Router02.sol';

interface Structs {
    struct Val {
        uint256 value;
    }

    enum ActionType {
      Deposit,   // supply tokens
      Withdraw,  // borrow tokens
      Transfer,  // transfer balance between accounts
      Buy,       // buy an amount of some token (externally)
      Sell,      // sell an amount of some token (externally)
      Trade,     // trade tokens against another account
      Liquidate, // liquidate an undercollateralized or expiring account
      Vaporize,  // use excess tokens to zero-out a completely negative account
      Call       // send arbitrary data to an address
    }

    enum AssetDenomination {
        Wei // the amount is denominated in wei
    }

    enum AssetReference {
        Delta // the amount is given as a delta from the current value
    }

    struct AssetAmount {
        bool sign; // true if positive
        AssetDenomination denomination;
        AssetReference ref;
        uint256 value;
    }

    struct ActionArgs {
        ActionType actionType;
        uint256 accountId;
        AssetAmount amount;
        uint256 primaryMarketId;
        uint256 secondaryMarketId;
        address otherAddress;
        uint256 otherAccountId;
        bytes data;
    }

    struct Info {
        address owner;  // The address that owns the account
        uint256 number; // A nonce that allows a single address to control many accounts
    }

    struct Wei {
        bool sign; // true if positive
        uint256 value;
    }
}

/**
 * @dev Interface of the ERC20 standard as defined in the EIP. Does not include
 * the optional functions; to access them see `ERC20Detailed`.
 */
interface IERC20 {
    function totalSupply() external view returns (uint256);
    function balanceOf(address account) external view returns (uint256);
    function transfer(address recipient, uint256 amount) external returns (bool);
    function allowance(address owner, address spender) external view returns (uint256);
    function approve(address spender, uint256 amount) external returns (bool);
    function transferFrom(address sender, address recipient, uint256 amount) external returns (bool);
    event Transfer(address indexed from, address indexed to, uint256 value);
    event Approval(address indexed owner, address indexed spender, uint256 value);
}

abstract contract DyDxPool is Structs {
    function operate(Info[] memory, ActionArgs[] memory) virtual public;
}

contract DyDxFlashLoan is Structs {
    // all addresses are for mainnet
    DyDxPool pool = DyDxPool(0x1E0447b19BB6EcFdAe1e4AE1694b0C3659614e4e);

    address public DAI_ADD = 0x6B175474E89094C44Da98b954EedeAC495271d0F;

    function flashloan(uint256 amount, bytes memory data)
        internal
    {
        IERC20(DAI_ADD).approve(address(pool), amount + 1);
        Info[] memory infos = new Info[](1);
        ActionArgs[] memory args = new ActionArgs[](3);

        infos[0] = Info(address(this), 0);

        AssetAmount memory withdrawAmount = AssetAmount(
            false,
            AssetDenomination.Wei,
            AssetReference.Delta,
            amount
        );
        ActionArgs memory withdraw;
        withdraw.actionType = ActionType.Withdraw;
        withdraw.accountId = 0;
        withdraw.amount = withdrawAmount;
        withdraw.primaryMarketId = 3;
        withdraw.otherAddress = address(this);

        args[0] = withdraw;

        ActionArgs memory call;
        call.actionType = ActionType.Call;
        call.accountId = 0;
        call.otherAddress = address(this);
        call.data = data;

        args[1] = call;

        ActionArgs memory deposit;
        AssetAmount memory depositAmount = AssetAmount(
            true,
            AssetDenomination.Wei,
            AssetReference.Delta,
            amount + 1
        );
        deposit.actionType = ActionType.Deposit;
        deposit.accountId = 0;
        deposit.amount = depositAmount;
        deposit.primaryMarketId = 3;
        deposit.otherAddress = address(this);

        args[2] = deposit;

        pool.operate(infos, args);
    }
}


contract Bot is DyDxFlashLoan {
    
    // all addresses are for mainnet
    address payable owner;

    // address public DAI_ADD = 0x6B175474E89094C44Da98b954EedeAC495271d0F;
    address public WETH_ADD = 0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2;

    // ERC20 tokens
    IERC20 DAI_TOKEN = IERC20(DAI_ADD);
    IERC20 WETH_TOKEN = IERC20(WETH_ADD);

    // ZeroX addresses
    address ZERO_X_EXCHANGE_ADD = 0x61935CbDd02287B511119DDb11Aeb42F1593b7Ef;
    address ZERO_X_ERC20_PROXY_ADD = 0x95E6F48254609A6ee006F7D493c8e5fB97094ceF;
    address ZERO_X_STAKING_ADD = 0xa26e80e7Dea86279c6d778D702Cc413E6CFfA777;

    // Uniswap addresses
    address UNISWAP_ROUTER_ADDRESS = 0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D;

    modifier onlyOwner() {
        require(msg.sender == owner);
        _;
    }

    receive() external payable  {}

    constructor() public payable {
        owner = msg.sender;

        // approve 0x for trading fee
        WETH_TOKEN.approve(ZERO_X_STAKING_ADD, msg.value);
    }

    function startTrade(uint256 daiAmount, uint256 wethAmount, bytes calldata zeroXData ) external payable onlyOwner {
        uint256 daiBeforeBalance = DAI_TOKEN.balanceOf(address(this));
        bytes memory data = abi.encode(daiAmount, wethAmount, zeroXData, daiBeforeBalance);
        flashloan(daiAmount, data);

    }

    function callFunction(
        address, 
        Info calldata, 
        bytes calldata data
    ) external {
        (uint256 daiAmount, uint256 wethAmount, bytes memory zeroXData, uint256 daiBeforeBalance) = abi.decode(data, (uint256, uint256, bytes, uint256));
        uint256 daiAfterBalance = DAI_TOKEN.balanceOf(address(this));

        require(daiBeforeBalance - daiAfterBalance == daiAmount);

        trade(daiAmount, zeroXData);
    }

    function trade(uint256 daiAmount, bytes memory zeroXData) onlyOwner payable public {
        uint256 daiBeforeTrade = DAI_TOKEN.balanceOf(address(this));
        uint256 wethBeforeTrade = WETH_TOKEN.balanceOf(address(this));

        // perform zeroX trade
        DAI_TOKEN.approve(ZERO_X_ERC20_PROXY_ADD, daiAmount);
        address(ZERO_X_EXCHANGE_ADD).call{value:msg.value}(zeroXData);
        DAI_TOKEN.approve(ZERO_X_ERC20_PROXY_ADD, 0);

        // calculate WETH received
        uint256 wethAfterTrade = WETH_TOKEN.balanceOf(address(this));
        uint256 wethAmount = wethBeforeTrade - wethAfterTrade;

        // perform uniswap trade
        WETH_TOKEN.approve(UNISWAP_ROUTER_ADDRESS, wethAmount);
        // setting up router path
        address[] memory path = new address[](2);
        path[0] = WETH_ADD;
        path[1] = DAI_ADD;
        IUniswapV2Router02(UNISWAP_ROUTER_ADDRESS).swapExactTokensForTokens(wethAmount, daiAmount, path, address(this), block.timestamp);

        uint256 daiAfterTrade = DAI_TOKEN.balanceOf(address(this));

        require(daiAfterTrade > daiBeforeTrade);
    }

    function withdramDai() public onlyOwner {
        uint256 balance = DAI_TOKEN.balanceOf(address(this));
        DAI_TOKEN.transfer(owner, balance);
    }
}