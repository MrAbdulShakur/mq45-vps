from utils.database import supabase
from datetime import datetime, timezone
from collections import defaultdict
from loguru import logger
import asyncio
from dateutil.relativedelta import relativedelta


TRADE_DEAL_TYPES = {
    0: "BUY",
    1: "SELL",
    2: "BALANCE",
    3: "CREDIT",
    4: "CHARGE",
    5: "CORRECTION",
    6: "BONUS",
    7: "COMMISSION",
    8: "COMMISSION_DAILY",
    9: "COMMISSION_MONTHLY",
    10: "COMMISSION_AGENT_DAILY",
    11: "COMMISSION_AGENT_MONTHLY",
    12: "INTEREST",
    13: "BUY_CANCELED",
    14: "SELL_CANCELED",
    15: "DIVIDEND",
    16: "DIVIDEND_FRANKED",
    17: "TAX"
}
TRADE_ENTRY_TYPES = {0: "DEAL_ENTRY_IN", 1: "DEAL_ENTRY_OUT",
                     2: "DEAL_ENTRY_INOUT", 3: "DEAL_ENTRY_OUT_BY"}
TRADE_DEAL_REASON_TYPES = {
    0: "DEAL_REASON_CLIENT",       # Manual trade from desktop terminal
    1: "DEAL_REASON_MOBILE",       # Manual trade from mobile app
    2: "DEAL_REASON_WEB",          # Manual trade from web terminal
    3: "DEAL_REASON_EXPERT",       # Trade executed by Expert Advisor or script
    4: "DEAL_REASON_SL",           # Stop Loss triggered
    5: "DEAL_REASON_TP",           # Take Profit triggered
    6: "DEAL_REASON_SO",           # Stop Out (margin call)
    7: "DEAL_REASON_ROLLOVER",     # Rollover/swap execution
    8: "DEAL_REASON_VMARGIN",      # Variation margin operation
    9: "DEAL_REASON_SPLIT"         # Position split or symbol change by broker
}

TRADE_MODES = {
    0: "ACCOUNT_TRADE_MODE_DEMO",
    1: "ACCOUNT_TRADE_MODE_CONTEST",
    2: "ACCOUNT_TRADE_MODE_REAL"
}

MARGIN_MODES = {
    0: "ACCOUNT_MARGIN_MODE_RETAIL_NETTING",
    1: "ACCOUNT_MARGIN_MODE_EXCHANGE",
    2: "ACCOUNT_MARGIN_MODE_RETAIL_HEDGING"
}

DELAY_FOR_ACCOUNT_FETCH = 0
DELAY_FOR_ACCOUNT_FETCH_RE_ENTRY = 0.25

class TerminalManager:
    import MetaTrader5 as mt5
    retry_limit = 3

    def __init__(self):
        self.symbols_info = {}

    async def get_available_terminal(terminal_number = None):
        if terminal_number and terminal_number != 0:
            logger.success(f"🟢 Terminal T{terminal_number} allocated.")
            return {
                "status": True,
                "message": f"🟢 Terminal T{terminal_number} allocated.",
                "data": {
                    "id": f"T{terminal_number}",
                    "path": f"C:\\MQ45\\Terminals\\T{terminal_number}\\terminal64.exe"
                }
            }
            
        response = (
            supabase.rpc("allocate_free_mt5_terminal")
            .execute()
        )

        terminals = response.data

        if len(terminals):
            logger.success(f"🟢 Terminal {terminals[0].get("id")} allocated.")
            return {
                "status": True,
                "message": f"🟢 Terminal {terminals[0].get("id")} allocated.",
                "data": {
                    "id": terminals[0].get("id"),
                    "path": terminals[0].get("path")
                }
            }
        else:
            return {
                "status": False,
                "message": "❌ No free terminals."
            }

    async def release_terminal(terminal_id: str, terminal_number = None):
        if terminal_number and terminal_number != 0:
            logger.success(f"🔵 Terminal {terminal_id} released.")
            return True
        
        try:
            response = (
                supabase.table("mt5_terminals")
                .update({"in_use": False})
                .eq("id", terminal_id)
                .execute()
            )

            if len(response.data):
                logger.success(f"🔵 Terminal {terminal_id} released.")
                return True
            else:
                return False
        except Exception as e:
            logger.warning(f"❌ Failed to release terminal {terminal_id}: {e}")
            return False
        

    async def get_refined_account_data(self, login: str, password: str, server: str, start_date, end_date):
        # Shut down any existing connection
        self.mt5.shutdown()
        terminal = await TerminalManager.get_available_terminal()

        if not terminal.get("status"):
            logger.warning(terminal.get("message"))
            return {
                "status": False,
                "message": terminal.get("message")
            }

        def initialize_mt5():
            # logic to retry empty initialize_mt5
            for attempt in range(self.retry_limit):
                initialize = self.mt5.initialize(path=terminal.get("data").get(
                    "path"), login=login, password=password, server=server, timeout=5000, portable=True)
                
                if initialize:
                    return initialize
                logger.info(f"Attempt {attempt + 1} failed for initialize_mt5")
            
            return None
        
        initialize = initialize_mt5()

        if not initialize:
            error = self.mt5.last_error()
            self.mt5.shutdown()
            await TerminalManager.release_terminal(terminal.get("data").get("id"))
            logger.warning(f"abort mt op -> {error[1]}")
            
            if error and error[0] == -6 and error[1] == "Terminal: Authorization failed":
                return {
                    "status": False,
                    "message": f"❌ Invalid trading account credentials"
                }
            else:
                return {
                    "status": False,
                    "message": f"❌ Could not initailize trading account"
                }
        
        await asyncio.sleep(DELAY_FOR_ACCOUNT_FETCH)
        
        # history deals
        history_deals = await self.get_history_deals(start_date, end_date)
        
        # balance trades
        balance_trades = TerminalManager.get_balance_trades(history_deals)

        # closed positions
        closed_trades = await self.get_closed_trades(history_deals)

        # open positions
        open_trades = await self.get_open_trades()

        # account info
        account_info = await self.get_account_info(open_trades, closed_trades, balance_trades)

        self.mt5.shutdown()
        await TerminalManager.release_terminal(terminal.get("data").get("id"))

        return {
            "status": True,
            "message": "🟢 Account synced and verified successfully",
            "data": {
                "account_info": account_info,
                "balance_trades": balance_trades,
                "open_trades": open_trades,
                "closed_trades": closed_trades

            }
        }

    async def get_account_info(self, open_trades, closed_trades, balance_trades):
        # logic to retry empty account_info
        async def account_info():
            for attempt in range(self.retry_limit):
                info = self.mt5.account_info()
                if info:
                    return info
                logger.info(f"Attempt {attempt + 1} failed for account_info")
                await asyncio.sleep(DELAY_FOR_ACCOUNT_FETCH_RE_ENTRY)
            
            return None
        
        account_info = await account_info()
        if not account_info:
            return None

        account_info_dict = account_info._asdict()
        deposits = sum(t["profit"] for t in balance_trades if t["profit"] >= 0)
        withdrawals = sum(t["profit"] for t in balance_trades if t["profit"] < 0)
            
        total_trades = sum([len(open_trades), len(closed_trades)])


        winning_trades = [t for t in closed_trades if t["profit"] > 0] + [t for t in open_trades if t["profit"] > 0]
        average_win = sum(t["profit"] for t in winning_trades) / \
            len(winning_trades) if winning_trades else 0
        won_trades_percent = (len(winning_trades) /
                              len(closed_trades + open_trades)) * 100 if len(closed_trades + open_trades) > 0 else 0
        total_pips = sum(t.get("pips", 0) for t in closed_trades)

        closed_trades_profit = sum([d["profit"] for d in closed_trades])
        open_trades_profit = sum([d["profit"] for d in open_trades])
        total_profit = sum([closed_trades_profit, open_trades_profit])
        
        balance = account_info_dict["balance"]

        gain = (sum([d["gain"] for d in closed_trades]) / len(closed_trades)) if len(closed_trades) > 0 else 0

        swap = sum([d["swap"] for d in closed_trades]) + sum([d["swap"] for d in open_trades])

        return {
            "balance": balance,
            "leverage": account_info_dict["leverage"],
            "login": account_info_dict["login"],
            "trade_mode": TRADE_MODES.get(account_info_dict["trade_mode"], account_info_dict["trade_mode"]),
            "currency": account_info_dict["currency"],
            "equity": account_info_dict["equity"],
            "swap": swap,
            "profit": (balance - (withdrawals)) - deposits,
            "gain": gain,
            "deposits": deposits,
            "withdrawals": withdrawals,
            "trades": total_trades,
            "average_win": average_win,
            "margin_mode": MARGIN_MODES.get(account_info_dict["margin_mode"], account_info_dict["margin_mode"]),
            "won_trades_percent": won_trades_percent,
            "pips": round(total_pips / 1000, 2),
            "commission_blocked": account_info_dict["commission_blocked"],
            "name": account_info_dict["name"],
            "company": account_info_dict["company"],
            "limit_orders": account_info_dict["limit_orders"],
            "margin_so_mode": account_info_dict["margin_so_mode"],
            "trade_allowed": account_info_dict["trade_allowed"],
            "trade_expert": account_info_dict["trade_expert"],
            "currency_digits": account_info_dict["currency_digits"],
            "fifo_close": account_info_dict["fifo_close"],
            "credit": account_info_dict["credit"],
            "margin": account_info_dict["margin"],
            "margin_free": account_info_dict["margin_free"],
            "margin_level": account_info_dict["margin_level"],
            "margin_so_call": account_info_dict["margin_so_call"],
            "margin_so_so": account_info_dict["margin_so_so"],
            "margin_initial": account_info_dict["margin_initial"],
            "margin_maintenance": account_info_dict["margin_maintenance"],
            "assets": account_info_dict["assets"],
            "liabilities": account_info_dict["liabilities"]
        }

    async def get_history_deals(self, user_start_date = None, user_end_date = None):
        # logic to retry empty history deals
        async def history_deals():
            start_date = ""
            end_date = ""

            if user_start_date and user_end_date:
                start_date = datetime.fromisoformat(user_start_date)
                end_date = datetime.fromisoformat(user_end_date) + relativedelta(days=1)
            else:
                end_date = datetime.now()
                start_date = (end_date - relativedelta(years=1)) + relativedelta(days=1)

            for attempt in range(self.retry_limit):
                deals = self.mt5.history_deals_get(start_date, end_date)
                if deals:
                    return deals
                logger.info(f"Attempt {attempt + 1} failed for get_history_deals")
                await asyncio.sleep(DELAY_FOR_ACCOUNT_FETCH_RE_ENTRY)
            
            return None
        

        deals = await history_deals()
        
        if not deals:
            logger.warning("deals -> ", self.mt5.last_error())
            return []

        return [d._asdict() for d in deals]


    async def get_symbol_info(self, symbol):
        try:
            existing_symbol_info = self.symbols_info.get(symbol, False)
            
            if existing_symbol_info:
                return existing_symbol_info

            if self.mt5.symbol_select(symbol, True):
                # logic to retry empty symbol info
                async def get_symbols():
                    for attempt in range(self.retry_limit):
                        info = self.mt5.symbol_info(symbol)
                        if info:
                            return info
                        logger.info(f"Attempt {attempt + 1} failed for get_symbol_info")
                        await asyncio.sleep(DELAY_FOR_ACCOUNT_FETCH_RE_ENTRY)
                    
                    return None
        
                info = await get_symbols()
                
                if info:
                    symbol_dict = info._asdict()
                    new_symbol_info = {
                        "trade_contract_size": symbol_dict.get("trade_contract_size", 0)
                    }
                    
                    self.symbols_info[symbol] = new_symbol_info
                    
                    return new_symbol_info

            logger.warning("symbol -> ", self.mt5.last_error())
        except Exception as e:
            logger.warning("❌ Failed to get symbol data")

        return

    def get_trade_change_percent(contract_size, volume, open_price, profit):        
        # Trade notional value = volume (lots) × contract size × open price
        notional_value = volume * contract_size * open_price

        if notional_value == 0:
            return 0.0
        
        # Change % = profit ÷ notional_value × 100
        change_percent = (profit / notional_value) * 100
        return change_percent


    async def get_open_trades(self):
        # logic to retry empty open trades
        async def get_positions():
            for attempt in range(self.retry_limit):
                positions = self.mt5.positions_get()
                if positions:
                    return positions
                logger.info(f"Attempt {attempt + 1} failed for get_open_trades")
                await asyncio.sleep(DELAY_FOR_ACCOUNT_FETCH_RE_ENTRY)
            
            return None
        
        positions = await get_positions()

        if not positions:
            logger.warning("positions -> ", self.mt5.last_error())
            return []

        open_trades = [d._asdict() for d in positions]
        result = []

        for open_trade in open_trades:
            open_time = datetime.fromtimestamp(
                open_trade["time_msc"]/1000, tz=timezone.utc)
            duration = (datetime.now(timezone.utc) -
                        open_time).total_seconds() / 60
            gain = ((open_trade["profit"] / (open_trade["price_open"] *
                    open_trade["volume"])) * 100) if open_trade["price_open"] > 0 else 0
            
            symbol = open_trade["symbol"]
            symbol_info = await self.get_symbol_info(symbol)

            contract_size = symbol_info.get("trade_contract_size", 0)
            
            change_percent = TerminalManager.get_trade_change_percent(contract_size, open_trade["volume"], open_trade["price_open"], open_trade["profit"])

            open_trade_data = {
                "trade_id": str(open_trade["identifier"]),
                "symbol": symbol,
                "volume": open_trade["volume"],
                "magic": open_trade["magic"],
                "reason": open_trade["reason"],
                "swap": open_trade["swap"],
                "open_time": open_time.isoformat(),
                "open_price": open_trade["price_open"],
                "market_value": open_trade["price_current"],
                "profit": open_trade["profit"],
                "stop_loss": open_trade["sl"],
                "take_profit": open_trade["tp"],
                "change_percent": change_percent,
                "gain": gain,
                "duration_in_minutes": round(duration),
                "type": "BUY" if open_trade["type"] == 0 else "SELL",
                "success": "won" if open_trade["profit"] > 0 else "lost"
            }
            result.append(open_trade_data)

        return result

    
    async def get_closed_trades(self, history_deals: list):
        # group deals by position_id (only positive position ids)
        trades_by_position = defaultdict(list)
        for d in history_deals:
            pid = d.get("position_id", 0)
            if pid and pid > 0:
                trades_by_position[pid].append(d)

        result = []

        for position_id, deals in trades_by_position.items():
            # split into opens, closes and others
            open_deals = [d for d in deals if d.get("entry") == 0]
            close_deals = [d for d in deals if d.get("entry") == 1]
            if not open_deals or not close_deals:
                # skip if not a fully opened & closed position (you can change this behavior)
                continue

            # totals and VWAPs
            total_open_vol = sum(d.get("volume", 0.0) for d in open_deals)
            total_close_vol = sum(d.get("volume", 0.0) for d in close_deals) or total_open_vol

            # VWAP open price (weighted by volume)
            open_price_vwap = sum(d.get("price", 0.0) * d.get("volume", 0.0) for d in open_deals) / total_open_vol
            close_price_vwap = sum(d.get("price", 0.0) * d.get("volume", 0.0) for d in close_deals) / total_close_vol

            # aggregate fees/swaps/commissions and raw profit
            total_commission = sum(d.get("commission", 0.0) for d in deals)
            total_swap = sum(d.get("swap", 0.0) for d in deals)
            total_fee = sum(d.get("fee", 0.0) for d in deals)
            total_profit_only = sum(d.get("profit", 0.0) for d in deals)

            # terminal-style net profit for the position (what the terminal shows)
            profit_net = total_profit_only + total_swap + total_commission + total_fee

            # times (use time_msc when available)
            open_time_ms = min(d.get("time_msc", d.get("time", 0) * 1000) for d in open_deals)
            close_time_ms = max(d.get("time_msc", d.get("time", 0) * 1000) for d in close_deals)
            open_time = datetime.fromtimestamp(open_time_ms / 1000.0, tz=timezone.utc)
            close_time = datetime.fromtimestamp(close_time_ms / 1000.0, tz=timezone.utc)
            duration_minutes = (close_time - open_time).total_seconds() / 60.0

            # direction & representative fields (take from first open deal)
            rep_open = open_deals[0]
            rep_close = close_deals[-1]
            direction = TRADE_DEAL_TYPES.get(rep_open.get("type"), "UNKNOWN")
            symbol = rep_open.get("symbol")

            # symbol info (await your existing symbol lookup)
            symbol_info = await self.get_symbol_info(symbol)
            contract_size = symbol_info.get("trade_contract_size", 1)
            digits = symbol_info.get("digits", 5)

            # price diff, market value and pips
            if direction == "BUY":
                price_diff = close_price_vwap - open_price_vwap
            else:
                price_diff = open_price_vwap - close_price_vwap

            market_value = price_diff * total_open_vol * contract_size

            # pip calculation: 1 pip = 10^(digits-1) for most instruments (works for XAU with digits=3 -> *100)
            pip_multiplier = 10 ** (max(digits - 1, 0))
            pips = round(price_diff * pip_multiplier, 2)

            # gain: profit relative to position notional (you can change denominator if you want gain vs account)
            entry_notional = open_price_vwap * total_open_vol * contract_size
            gain = (profit_net / entry_notional * 100) if entry_notional > 0 else 0.0

            # change percent using your TerminalManager helper (pass profit_net so it reflects full P/L)
            change_percent = TerminalManager.get_trade_change_percent(
                contract_size, total_open_vol, open_price_vwap, profit_net
            )

            # build the exact shape you were previously returning, but with aggregated values
            closed_trade_data = {
                "trade_id": str(position_id),
                "symbol": symbol,
                "type": direction,
                "volume": total_open_vol,
                "entry": rep_open.get("entry"),
                "magic": rep_open.get("magic"),
                "reason": rep_open.get("reason"),
                # return aggregated commission/swap/fee for the position
                "commission": total_commission,
                "swap": total_swap,
                "fee": total_fee,
                # profit is the net P/L (profit + swap + commission + fee) to match terminal
                "profit": profit_net,
                "open_time": open_time.isoformat(),
                "close_time": close_time.isoformat(),
                "open_price": open_price_vwap,
                "close_price": close_price_vwap,
                "market_value": market_value,
                "pips": pips,
                "gain": gain,
                "change_percent": change_percent,
                "duration_in_minutes": round(duration_minutes),
                "success": "won" if profit_net > 0 else "lost"
            }

            result.append(closed_trade_data)

        return result


    def get_balance_trades(history_deals: list):
        return [d for d in history_deals if d["type"] == 2]
    

    async def get_raw_account_data(self, login, password, server):
        self.mt5.shutdown()
        terminal = await TerminalManager.get_available_terminal()
        
        if not terminal.get("status"):
            logger.warning(terminal.get("message"))
            return {
                "status": False,
                "message": terminal.get("message")
            }

        def initialize_mt5():
            # logic to retry empty initialize_mt5
            for attempt in range(self.retry_limit):
                initialize = self.mt5.initialize(path=terminal.get("data").get(
                    "path"), login=login, password=password, server=server, timeout=5000, portable=True)
                
                if initialize:
                    return initialize
                logger.info(f"Attempt {attempt + 1} failed for initialize_mt5")
            
            return None
        
        initialize = initialize_mt5()

        if not initialize:
            error = self.mt5.last_error()
            self.mt5.shutdown()
            await TerminalManager.release_terminal(terminal.get("data").get("id"))
            logger.warning(f"abort mt op -> {error[1]}")
            
            if error and error[0] == -6 and error[1] == "Terminal: Authorization failed":
                return {
                    "status": False,
                    "message": f"❌ Invalid trading account credentials"
                }
            else:
                return {
                    "status": False,
                    "message": f"❌ Could not initailize trading account"
                } 
        
        await asyncio.sleep(DELAY_FOR_ACCOUNT_FETCH)

        async def account_info():
            for attempt in range(self.retry_limit):
                info = self.mt5.account_info()
                if info:
                    return info
                logger.info(f"Attempt {attempt + 1} failed for account_info")
                await asyncio.sleep(DELAY_FOR_ACCOUNT_FETCH_RE_ENTRY)
            
            return None
        account_info = await account_info()._asdict()
        
        
        async def get_positions():
            for attempt in range(self.retry_limit):
                positions = self.mt5.positions_get()
                if positions:
                    return positions
                logger.info(f"Attempt {attempt + 1} failed for get_positions")
                await asyncio.sleep(DELAY_FOR_ACCOUNT_FETCH_RE_ENTRY)
            
            return None
        positions = [p._asdict() for p in await get_positions() or []]


        async def history_deals():
            end_date = datetime.now()
            start_date = end_date - relativedelta(years=1)
        
            for attempt in range(self.retry_limit):
                history = self.mt5.history_deals_get(
                    start_date, end_date)
                if history:
                    return history
                logger.info(f"Attempt {attempt + 1} failed for history_deals")
                await asyncio.sleep(DELAY_FOR_ACCOUNT_FETCH_RE_ENTRY)
            
            return None
        
        history = [d._asdict() for d in await history_deals() or []]
        
        
        self.mt5.shutdown()
        await TerminalManager.release_terminal(terminal.get("data").get("id"))

        return {
            "status": True,
            "message": "🟢 Account fetched successfully",
            "data": {
                "account_info": account_info,
                "positions": positions,
                "history_deals": history
            }
        }
