import os
import sys
import json
import time
import signal
import asyncio
import logging
from threading import Thread
from queue import Queue

import telegram
from oandapyV20 import API
from oandapyV20.endpoints import orders, accounts, instruments, positions

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

# --- Load env ---
from dotenv import load_dotenv
load_dotenv()

# Constants from env
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
OANDA_API_KEY = os.getenv("OANDA_API_KEY")
OANDA_ACCOUNT_ID = os.getenv("OANDA_ACCOUNT_ID")

if not all([TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, OANDA_API_KEY, OANDA_ACCOUNT_ID]):
    logger.error("Missing critical environment variables. Exiting.")
    sys.exit(1)

# Max risk parameters
MAX_DAILY_LOSS_PERCENT = float(os.getenv("MAX_DAILY_LOSS_PERCENT", "20"))  # Stop bot if loss >= 20% daily
MAX_CAPITAL_LOSS_PERCENT = 70  # Hard stop if losing more than 70% total capital

# Scan interval seconds
SCAN_INTERVAL = float(os.getenv("SCAN_INTERVAL", "1"))

# Persistent state file path
STATE_FILE = "data/state.json"
os.makedirs("data", exist_ok=True)

class StateManager:
    def __init__(self, filepath):
        self.filepath = filepath
        self.state = {
            "running": False,
            "daily_profit_loss": 0.0,
            "weekly_profit_loss": 0.0,
            "total_capital": 10000.0,  # starting demo capital
            "last_trade": None,
            "trades": [],
            "recovery_mode": False,
        }
        self.load()

    def load(self):
        try:
            with open(self.filepath, "r") as f:
                self.state.update(json.load(f))
                logger.info("State loaded")
        except Exception:
            logger.info("No previous state found, starting fresh")

    def save(self):
        try:
            with open(self.filepath, "w") as f:
                json.dump(self.state, f, indent=2)
                logger.debug("State saved")
        except Exception as e:
            logger.error(f"Failed to save state: {e}")

state_mgr = StateManager(STATE_FILE)

# --- Initialize OANDA API ---
api = API(access_token=OANDA_API_KEY)

# --- Core Trader instance ---
trader = Trader(api, OANDA_ACCOUNT_ID, state_mgr, logger)

# --- Market scraper instance ---
scraper = MarketSentimentScraper(logger)

# --- Telegram Bot instance ---
tg_bot = TelegramBot(
    token=TELEGRAM_BOT_TOKEN,
    chat_id=TELEGRAM_CHAT_ID,
    logger=logger
)

# Telegram command queue for main thread to process
command_queue = Queue()

def telegram_listener():
    tg_bot.start_polling(command_queue)

async def trading_loop():
    logger.info("Trading loop started")
    while True:
        if not state_mgr.state["running"]:
            await asyncio.sleep(1)
            continue

        # Run scraper async to update sentiment
        sentiment = await scraper.fetch_latest_sentiment()

        # Run trader scan + trade with sentiment & latest data
        trade_report = await trader.analyze_and_trade(sentiment)

        if trade_report:
            tg_bot.send_message(trade_report)

        # Check risk limits
        if abs(state_mgr.state["daily_profit_loss"]) >= MAX_DAILY_LOSS_PERCENT / 100 * state_mgr.state["total_capital"]:
            logger.warning("Max daily loss reached, stopping bot for the day")
            state_mgr.state["running"] = False
            state_mgr.state["recovery_mode"] = True
            tg_bot.send_message("🚫 Daily loss limit reached. Bot stopped for the day. Recovery mode enabled.")
            state_mgr.save()

        if abs(state_mgr.state["total_capital"] - 10000.0) / 10000.0 >= MAX_CAPITAL_LOSS_PERCENT / 100:
            logger.error("Total capital loss exceeded hard limit. Stopping bot permanently.")
            state_mgr.state["running"] = False
            tg_bot.send_message("💀 Hard capital loss limit exceeded. Bot permanently stopped.")
            state_mgr.save()
            sys.exit(1)

        # Save state every loop
        state_mgr.save()

        await asyncio.sleep(SCAN_INTERVAL)

def handle_telegram_commands():
    while True:
        cmd = command_queue.get()
        if cmd == "/start":
            if state_mgr.state["running"]:
                tg_bot.send_message("Bot already running.")
            else:
                state_mgr.state["running"] = True
                state_mgr.save()
                strategy_summary = trader.get_strategy_summary()
                tg_bot.send_message(f"✅ Bot started.\nStrategy today:\n{strategy_summary}")

        elif cmd == "/stop":
            if not state_mgr.state["running"]:
                tg_bot.send_message("Bot already stopped.")
            else:
                state_mgr.state["running"] = False
                state_mgr.save()
                tg_bot.send_message("🛑 Bot stopped.\nCheck logs for issues if any.")

        elif cmd == "/maketrade":
            trade_report = asyncio.run(trader.force_trade())
            tg_bot.send_message(trade_report)

        elif cmd == "/diagnostic":
            diag = trader.run_diagnostics()
            tg_bot.send_message(f"🩺 Diagnostics:\n{diag}")

        elif cmd == "/daily":
            pnl = state_mgr.state["daily_profit_loss"]
            expected = trader.estimate_daily_profit()
            tg_bot.send_message(f"📅 Today's P&L: £{pnl:.2f}\nExpected EOD: £{expected:.2f}")

        elif cmd == "/weekly":
            pnl = state_mgr.state["weekly_profit_loss"]
            expected = trader.estimate_weekly_profit()
            tg_bot.send_message(f"🗓️ This week's P&L: £{pnl:.2f}\nExpected EOW: £{expected:.2f}")

        else:
            tg_bot.send_message("❓ Unknown command.")

def shutdown_handler(sig, frame):
    logger.info("Shutdown signal received. Stopping bot.")
    state_mgr.state["running"] = False
    state_mgr.save()
    sys.exit(0)

if __name__ == "__main__":
    # Signal handlers for clean exit
    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)

    logger.info("Starting AI Trading Bot")

    # Start telegram listener thread
    tg_thread = Thread(target=telegram_listener, daemon=True)
    tg_thread.start()

    # Start telegram command processor thread
    cmd_thread = Thread(target=handle_telegram_commands, daemon=True)
    cmd_thread.start()

    # Run async trading loop in main thread event loop
    asyncio.run(trading_loop())                                                                                                                               