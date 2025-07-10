import os
import sys
import json
import time
import signal
import asyncio
import logging
from threading import Thread
from queue import Queue
from datetime import datetime

from oandapyV20 import API
from trader import Trader
from scraper import MarketSentimentScraper
from bot import TelegramBot

# --- Setup logging ---
LOG_PATH = "logs/trading_bot.log"
os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("main")

# --- Load ENV manually ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
OANDA_API_KEY = os.getenv("OANDA_API_KEY")
OANDA_ACCOUNT_ID = os.getenv("OANDA_ACCOUNT_ID")
HF_API_KEY = os.getenv("HF_API_KEY")

if not all([TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, OANDA_API_KEY, OANDA_ACCOUNT_ID, HF_API_KEY]):
    logger.error("❌ Missing critical environment variables.")
    sys.exit(1)

# Constants
STATE_FILE = "data/state.json"
os.makedirs("data", exist_ok=True)

# Setup
state = {
    "running": False,
    "daily_pnl": 0.0,
    "weekly_pnl": 0.0,
    "capital": 10000.0,
    "open_trades": [],
    "last_reset": datetime.now().isoformat()
}

# Save state
def save_state():
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)

# Load state
def load_state():
    try:
        with open(STATE_FILE, "r") as f:
            state.update(json.load(f))
    except:
        save_state()

load_state()

# --- Components ---
api = API(access_token=OANDA_API_KEY)
trader = Trader(api, OANDA_ACCOUNT_ID, state, logger)
scraper = MarketSentimentScraper(logger, HF_API_KEY)
bot = TelegramBot(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, logger)
command_queue = Queue()

# --- Telegram listener ---
def telegram_listener():
    try:
        bot.start_polling(command_queue)
    except Exception as e:
        logger.error(f"Telegram listener error: {e}")

# --- Command handler ---
def handle_telegram_commands():
    while True:
        cmd = command_queue.get()
        logger.info(f"Processing command: {cmd}")
        try:
            if cmd == "/start":
                if state["running"]:
                    bot.send_message("🤖 Already running.")
                else:
                    state["running"] = True
                    save_state()
                    bot.send_message("✅ Bot started.")
            elif cmd == "/stop":
                state["running"] = False
                save_state()
                bot.send_message("🛑 Bot stopped.")
            elif cmd == "/status":
                summary = trader.status_summary(state)
                bot.send_message(summary)
            elif cmd == "/whatyoudoin":
                report = trader.activity_report()
                bot.send_message(report)
            elif cmd == "/daily":
                pnl = state["daily_pnl"]
                expected = trader.estimate_daily_profit()
                bot.send_message(f"📅 Today's P&L: £{pnl:.2f}\n📈 Expected EOD: £{expected:.2f}")
            elif cmd == "/weekly":
                pnl = state["weekly_pnl"]
                expected = trader.estimate_weekly_profit()
                bot.send_message(f"🗓 Weekly P&L: £{pnl:.2f}\n📈 Expected EOW: £{expected:.2f}")
            elif cmd == "/maketrade":
                report = asyncio.run(trader.force_trade())
                bot.send_message(report)
            elif cmd == "/help":
                help_text = """
📘 Commands:
/start - Start bot
/stop - Stop bot
/status - Full system & trading status
/whatyoudoin - Full activity report
/maketrade - Force trade now
/daily - Daily P&L
/weekly - Weekly P&L
/help - Show commands
"""
                bot.send_message(help_text)
        except Exception as e:
            logger.error(f"Command error: {e}")
            bot.send_message(f"⚠️ Command error: {str(e)}")

# --- Async trading loop ---
async def trading_loop():
    logger.info("📈 Starting trading loop")
    bot.send_message("🤖 Trading bot started and ready.")
    while True:
        try:
            if not state["running"]:
                await asyncio.sleep(5)
                continue

            # Reset daily P&L if new day
            now = datetime.now()
            last = datetime.fromisoformat(state["last_reset"])
            if now.date() > last.date():
                state["daily_pnl"] = 0.0
                state["last_reset"] = now.isoformat()
                save_state()

            # Scrape sentiment
            sentiment = await scraper.fetch()

            # Analyze + trade
            report = await trader.analyze_and_trade(sentiment)
            if report:
                bot.send_message(report)

            save_state()
        except Exception as e:
            logger.error(f"❌ Loop error: {e}")
            bot.send_message(f"⚠️ Loop error: {str(e)}")
            await asyncio.sleep(10)

        await asyncio.sleep(20)

# --- Graceful shutdown ---
def shutdown(sig, frame):
    logger.info("👋 Shutting down")
    state["running"] = False
    save_state()
    bot.send_message("🛑 Bot shutting down.")
    sys.exit(0)

signal.signal(signal.SIGINT, shutdown)
signal.signal(signal.SIGTERM, shutdown)

if __name__ == "__main__":
    tg_thread = Thread(target=telegram_listener, daemon=True)
    tg_thread.start()

    cmd_thread = Thread(target=handle_telegram_commands, daemon=True)
    cmd_thread.start()

    asyncio.run(trading_loop())