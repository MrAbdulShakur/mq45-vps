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

CRYPTO_SYMBOLS = {
    "USTEC_x100": "US Tech 100 Index",
    "US30_x10": "US Wall Street 30 Index",
    "US500_x100": "US SPX 500 Index",
    "BTC": "Bitcoin",
    "ETH": "Ethereum",
    "LTC": "Litecoin",
    "BCH": "Bitcoin Cash",
    "XRP": "Ripple",
    "ADA": "Cardano",
    "DOT": "Polkadot",
    "SOL": "Solana",
    "DOGE": "Dogecoin",
    "EOS": "EOS",
    "FIL": "Filecoin",
    "TRX": "TRON",
    "UNI": "Uniswap",
    "XLM": "Stellar Lumens",
    "XMR": "Monero",
    "ZEC": "Zcash",
    "XTZ": "Tezos",
    "ALGO": "Algorand",
    "APE": "ApeCoin",
    "ATOM": "Cosmos (ATOM)",
    "AVAX": "Avalanche",
    "BNB": "Binance Coin",
    "LINK": "Chainlink",
    "MKR": "Maker",
    "NEO": "Neo",
    "IOT": "IOTA",
    "SOL": "Solana",
    "VET": "VeChain",
    "SXP": "SXP"
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
            supabase.rpc("allocate_free_terminal")
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
                supabase.table("terminals")
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
        
        
    def get_balance_trades(history_deals: list):
        return [d for d in history_deals if d["type"] == 2]
    

    async def get_account_data(self, login, password, server):
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
            
            if error and error[0] == -6 and error[1] == "Terminal: Authorization failed":
                logger.warning(f"abort mt op -> {error[1]}")
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
