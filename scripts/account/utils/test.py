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

            contract_size = symbol_info.get("trade_contract_size", 0)
            
            market_value = price_diff * open_trade["volume"] * contract_size
            change_percent = TerminalManager.get_trade_change_percent(contract_size, open_trade["volume"], open_trade["price"], close_trade["profit"])


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
                "change_percent": change_percent,
                "duration_in_minutes": round(duration_minutes),
                "success": "won" if close_trade["profit"] > 0 else "lost"
            }

            result.append(closed_trade_data)

        return result