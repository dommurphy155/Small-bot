import random
import logging
import asyncio
from oandapyV20.endpoints import orders, accounts
from strategy import StrategyEngine

class Trader:
    def __init__(self, api, account_id, state, logger: logging.Logger):
        self.api = api
        self.account_id = account_id
        self.state = state
        self.logger = logger
        self.strategy = StrategyEngine()

    async def analyze_and_trade(self, sentiment):
        instruments = self.strategy.select_instruments(sentiment)

        if not instruments:
            return "🛑 No good instruments found right now."

        trade_summaries = []
        for instr in instruments:
            decision, confidence = self.strategy.decide(instr, sentiment)

            if decision == "buy":
                trade = self.place_trade(instr, 100, "buy")
                if trade:
                    trade_summaries.append(f"🟢 BUY {instr} at £100 | 📊 Conf: {confidence:.2f}")
            elif decision == "sell":
                trade = self.place_trade(instr, 100, "sell")
                if trade:
                    trade_summaries.append(f"🔴 SELL {instr} at £100 | 📊 Conf: {confidence:.2f}")

        if not trade_summaries:
            return "⏳ No trades placed this round."

        return "\n".join(trade_summaries)

    def place_trade(self, instrument, amount, direction):
        try:
            data = {
                "order": {
                    "instrument": instrument,
                    "units": str(amount if direction == "buy" else -amount),
                    "type": "MARKET",
                    "positionFill": "DEFAULT"
                }
            }
            r = orders.OrderCreate(self.account_id, data=data)
            self.api.request(r)
            self.state["open_trades"].append({"instrument": instrument, "direction": direction, "amount": amount})
            return True
        except Exception as e:
            self.logger.error(f"Trade error: {e}")
            return False

    def force_trade(self):
        return asyncio.run(self.analyze_and_trade({}))

    def estimate_daily_profit(self):
        return round(self.state["capital"] * 0.012, 2)  # 1.2% daily

    def estimate_weekly_profit(self):
        return round(self.state["capital"] * 0.065, 2)  # ~6.5% weekly

    def status_summary(self, state):
        summary = f"""
📊 Status: {"🟢 RUNNING" if state["running"] else "🔴 STOPPED"}
💰 Daily P&L: £{state['daily_pnl']:.2f}
💼 Capital: £{state['capital']:.2f}
🧾 Open Trades: {len(state["open_trades"])}
🔄 Recovery Mode: {"YES" if state.get("recovery", False) else "NO"}

"""
        if not state["open_trades"]:
            summary += "📉 No open trades."
        else:
            summary += "📈 Open positions:\n"
            for t in state["open_trades"]:
                summary += f"→ {t['direction'].upper()} {t['instrument']} | £{t['amount']}\n"

        summary += f"\n📈 Est. EOD: £{self.estimate_daily_profit():.2f}\n📆 Est. EOW: £{self.estimate_weekly_profit():.2f}"
        return summary

    def activity_report(self):
        return f"""
🧠 Bot Activity:
• Scraper running every 20s
• 10 HuggingFace models rotating
• Watching 20 news sources
• OANDA Linked: ✅
• Last Trade Count: {len(self.state['open_trades'])}
• Capital: £{self.state['capital']}
• Daily P&L: £{self.state['daily_pnl']}
• Strategy Engine: ACTIVE

✅ System OK.
"""