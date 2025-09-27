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

DELAY_FOR_ACCOUNT_FETCH = 0.25

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
        
        # await asyncio.sleep(DELAY_FOR_ACCOUNT_FETCH)
        
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
        def account_info():
            for attempt in range(self.retry_limit):
                info = self.mt5.account_info()
                if info:
                    return info
                logger.info(f"Attempt {attempt + 1} failed for account_info")
            
            return None
        
        account_info = account_info()
        if not account_info:
            return None

        account_info_dict = account_info._asdict()
        starting_balance = sum(t["profit"] for t in balance_trades)
            
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
        
        equity = sum([starting_balance, total_profit])
        gain = ((equity - starting_balance) /
                starting_balance) * 100 if starting_balance > 0 else 0
        

        return {
            "balance": sum([starting_balance, closed_trades_profit]),
            "leverage": account_info_dict["leverage"],
            "trade_mode": TRADE_MODES.get(account_info_dict["trade_mode"], account_info_dict["trade_mode"]),
            "currency": account_info_dict["currency"],
            "equity": equity,
            "profit": total_profit,
            "gain": gain,
            "starting_balance": starting_balance,
            "trades": total_trades,
            "average_win": average_win,
            "margin_mode": MARGIN_MODES.get(account_info_dict["margin_mode"], account_info_dict["margin_mode"]),
            "won_trades_percent": won_trades_percent,
            "pips": round(total_pips / 1000, 2),
            "commission_blocked": 0,
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
        def history_deals():
            start_date = ""
            end_date = ""

            if user_start_date and user_end_date:
                start_date = datetime.fromisoformat(user_start_date)
                end_date = datetime.fromisoformat(user_end_date)
            else:
                end_date = datetime.now()
                start_date = end_date - relativedelta(years=1)
        
            for attempt in range(self.retry_limit):
                deals = self.mt5.history_deals_get(start_date, end_date)
                if deals:
                    return deals
                logger.info(f"Attempt {attempt + 1} failed for get_history_deals")
            
            return None
        

        deals = history_deals()
        
        if not deals:
            logger.warning("deals -> ", self.mt5.last_error())
            return []

        return [d._asdict() for d in deals]


    async def get_open_trades(self):
        # logic to retry empty open trades
        def get_positions():
            for attempt in range(self.retry_limit):
                positions = self.mt5.positions_get()
                if positions:
                    return positions
                logger.info(f"Attempt {attempt + 1} failed for get_open_trades")
            
            return None
        
        positions = get_positions()

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

            open_trade_data = {
                "trade_id": str(open_trade["identifier"]),
                "symbol": open_trade["symbol"],
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
                "gain": gain,
                "duration_in_minutes": round(duration),
                "type": "BUY" if open_trade["type"] == 0 else "SELL",
                "success": "won" if open_trade["profit"] > 0 else "lost"
            }
            result.append(open_trade_data)

        return result

    async def get_symbol_info(self, symbol):
        try:
            existing_symbol_info = self.symbols_info.get(symbol, False)
            if existing_symbol_info:
                return existing_symbol_info

            if self.mt5.symbol_select(symbol, True):
                # logic to retry empty symbol info
                def get_symbols():
                    for attempt in range(self.retry_limit):
                        info = self.mt5.symbol_info(symbol)
                        if info:
                            return info
                        logger.info(f"Attempt {attempt + 1} failed for get_symbol_info")
                    
                    return None
        
                info = get_symbols()
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


    async def get_closed_trades(self, history_deals: list):
        # only open and closed positions
        trades = [d for d in history_deals if d["type"] != 2]
        trades_by_position = defaultdict(dict)
        result = []
        
        for trade in trades:
            position_id = trade["position_id"]
            if trade["entry"] == 0:
                trades_by_position[position_id]["open"] = trade
            elif trade["entry"] == 1:
                trades_by_position[position_id]["close"] = trade

        for position_id, trade_pair in trades_by_position.items():
            open_trade = trade_pair.get("open")
            close_trade = trade_pair.get("close")

            if not open_trade or not close_trade:
                continue

            symbol = close_trade["symbol"]

            open_time = datetime.fromtimestamp(
                open_trade["time_msc"]/1000, tz=timezone.utc)
            close_time = datetime.fromtimestamp(
                close_trade["time_msc"]/1000, tz=timezone.utc)
            duration_minutes = (close_time - open_time).total_seconds() / 60

            direction = TRADE_DEAL_TYPES.get(open_trade["type"], "UNKNOWN")
            if direction == "BUY":
                pips = round(
                    (close_trade["price"] - open_trade["price"]) * 10**5, 2)
                price_diff = close_trade["price"] - open_trade["price"]
            else:  # SELL
                pips = round(
                    (open_trade["price"] - close_trade["price"]) * 10**5, 2)
                price_diff = open_trade["price"] - close_trade["price"]

            entry_value = open_trade["price"] * open_trade["volume"]
            gain = (close_trade["profit"] / entry_value *
                    100) if entry_value > 0 else 0

            symbol_info = await self.get_symbol_info(symbol)

            contract_size = symbol_info.get(
                symbol, {}).get("trade_contract_size", 0)
            market_value = price_diff * open_trade["volume"] * contract_size

            closed_trade_data = {
                "trade_id": str(position_id),
                "symbol": symbol,
                "type": direction,
                "volume": open_trade["volume"],
                "entry": open_trade["entry"],
                "magic": open_trade["magic"],
                "reason": open_trade["reason"],
                "commission": open_trade["commission"],
                "swap": open_trade["swap"],
                "fee": open_trade["fee"],
                "profit": close_trade["profit"],
                "open_time": open_time.isoformat(),
                "close_time": close_time.isoformat(),
                "open_price": open_trade["price"],
                "close_price": close_trade["price"],
                "market_value": market_value,
                "pips": round(pips / 1000, 2),
                "gain": gain,
                "duration_in_minutes": round(duration_minutes),
                "success": "won" if close_trade["profit"] > 0 else "lost"
            }

            result.append(closed_trade_data)

        return result


    def get_balance_trades(history_deals: list):
        return [d for d in history_deals if d["type"] == 2]
    

    async def get_raw_account_data(self, login, password, server):
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
        
        def account_info():
            for attempt in range(self.retry_limit):
                info = self.mt5.account_info()
                if info:
                    return info
                logger.info(f"Attempt {attempt + 1} failed for account_info")
            
            return None
        account_info = account_info()._asdict()
        
        await asyncio.sleep(DELAY_FOR_ACCOUNT_FETCH)
        
        def get_positions():
            for attempt in range(self.retry_limit):
                positions = self.mt5.positions_get()
                if positions:
                    return positions
                logger.info(f"Attempt {attempt + 1} failed for get_positions")
            
            return None
        positions = [p._asdict() for p in get_positions() or []]


        def history_deals():
            end_date = datetime.now()
            start_date = end_date - relativedelta(years=1)
        
            for attempt in range(self.retry_limit):
                history = self.mt5.history_deals_get(
                    start_date, end_date)
                if history:
                    return history
                logger.info(f"Attempt {attempt + 1} failed for history_deals")
            
            return None
        
        history = [d._asdict() for d in history_deals() or []]
        
        
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
