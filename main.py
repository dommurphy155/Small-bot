import os
import sys
import json
import time
import signal
import asyncio
import logging
import threading
from queue import Queue
from datetime import datetime

import telegram
from oandapyV20 import API
from oandapyV20.endpoints.pricing import Pricing
from oandapyV20.endpoints.orders import OrderCreate
from oandapyV20.endpoints.accounts import AccountDetails

from trader import Trader  # We'll assume this is your trading logic class
from scraper import MarketSentimentScraper  # Your scraper, async
from bot import TelegramBot  # Telegram wrapper you wrote

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
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    logger.warning("python-dotenv not found. Loading env variables from system.")

# --- Required environment variables ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
OANDA_API_KEY = os.getenv("OANDA_API_KEY")
OANDA_ACCOUNT_ID = os.getenv("OANDA_ACCOUNT_ID")

if not all([TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, OANDA_API_KEY, OANDA_ACCOUNT_ID]):
    logger.error("Missing one or more required environment variables: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, OANDA_API_KEY, OANDA_ACCOUNT_ID")
    sys.exit(1)

MAX_DAILY_LOSS_PERCENT = float(os.getenv("MAX_DAILY_LOSS_PERCENT", "20"))
MAX_CAPITAL_LOSS_PERCENT = 70  # hard stop at 70% loss
SCAN_INTERVAL = float(os.getenv("SCAN_INTERVAL", "30"))

STATE_FILE = "data/state.json"
os.makedirs("data", exist_ok=True)

state_lock = threading.Lock()

class StateManager:
    def __init__(self, filepath):
        self.filepath = filepath
        self.state = {
            "running": False,
            "daily_profit_loss": 0.0,
            "weekly_profit_loss": 0.0,
            "total_capital": 10000.0,
            "last_trade": None,
            "trades": [],
            "recovery_mode": False,
            "last_reset": datetime.now().isoformat(),
        }
        self.load()

    def load(self):
        with state_lock:
            try:
                with open(self.filepath, "r") as f:
                    loaded = json.load(f)
                    self.state.update(loaded)
                    logger.info("Loaded state from file.")
            except FileNotFoundError:
                logger.info("No existing state file. Starting fresh.")
                self.save()
            except Exception as e:
                logger.error(f"Error loading state file: {e}")
                self.save()

    def save(self):
        with state_lock:
            try:
                with open(self.filepath, "w") as f:
                    json.dump(self.state, f, indent=2)
            except Exception as e:
                logger.error(f"Error saving state file: {e}")

    def reset_daily_stats(self):
        with state_lock:
            self.state["daily_profit_loss"] = 0.0
            self.state["recovery_mode"] = False
            self.state["last_reset"] = datetime.now().isoformat()
            self.save()

state_mgr = StateManager(STATE_FILE)

# --- Initialize OANDA API ---
try:
    api = API(access_token=OANDA_API_KEY)
    logger.info("OANDA API initialized.")
except Exception as e:
    logger.error(f"Failed to init OANDA API: {e}")
    sys.exit(1)

# --- Initialize Trader, Scraper, TelegramBot ---
trader = Trader(api, OANDA_ACCOUNT_ID, state_mgr, logger)
scraper = MarketSentimentScraper(logger)
tg_bot = TelegramBot(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, logger)

command_queue = Queue()

def telegram_listener():
    try:
        tg_bot.start_polling(command_queue)
    except Exception as e:
        logger.error(f"Telegram listener crashed: {e}")

async def trading_loop():
    logger.info("Starting trading loop")
    tg_bot.send_message("🤖 Trading bot started and ready.")

    while True:
        try:
            if not state_mgr.state["running"]:
                await asyncio.sleep(5)
                continue

            now = datetime.now()
            last_reset = datetime.fromisoformat(state_mgr.state.get("last_reset", now.isoformat()))
            if now.date() > last_reset.date():
                state_mgr.reset_daily_stats()
                logger.info("Daily stats reset")

            sentiment = await scraper.fetch_latest_sentiment()
            trade_report = await trader.analyze_and_trade(sentiment)

            if trade_report:
                tg_bot.send_message(trade_report)

            # Check risk limits
            daily_loss_limit = MAX_DAILY_LOSS_PERCENT / 100 * state_mgr.state["total_capital"]
            if state_mgr.state["daily_profit_loss"] <= -daily_loss_limit:
                logger.warning(f"Daily loss limit reached: {state_mgr.state['daily_profit_loss']}")
                with state_lock:
                    state_mgr.state["running"] = False
                    state_mgr.state["recovery_mode"] = True
                    state_mgr.save()
                tg_bot.send_message(f"🚫 Daily loss limit reached (£{state_mgr.state['daily_profit_loss']:.2f}). Bot stopped.")
            
            capital_loss_pct = (10000.0 - state_mgr.state["total_capital"]) / 10000.0 * 100
            if capital_loss_pct >= MAX_CAPITAL_LOSS_PERCENT:
                logger.error(f"Capital loss exceeded: {capital_loss_pct:.2f}%")
                with state_lock:
                    state_mgr.state["running"] = False
                    state_mgr.save()
                tg_bot.send_message(f"💀 Capital loss limit exceeded ({capital_loss_pct:.1f}%). Bot stopped permanently.")
                sys.exit(1)

            state_mgr.save()

        except Exception as e:
            import traceback
            err = traceback.format_exc()
            logger.error(f"Trading loop error: {err}")
            tg_bot.send_message(f"⚠️ Trading loop error:\n{err}")

        await asyncio.sleep(SCAN_INTERVAL)

def handle_telegram_commands():
    while True:
        try:
            cmd = command_queue.get()
            logger.info(f"Command received: {cmd}")

            if cmd == "/start":
                with state_lock:
                    if state_mgr.state["running"]:
                        tg_bot.send_message("Bot already running.")
                    else:
                        state_mgr.state["running"] = True
                        state_mgr.save()
                        summary = trader.get_strategy_summary()
                        tg_bot.send_message(f"✅ Bot started.\n{summary}")

            elif cmd == "/stop":
                with state_lock:
                    if not state_mgr.state["running"]:
                        tg_bot.send_message("Bot already stopped.")
                    else:
                        state_mgr.state["running"] = False
                        state_mgr.save()
                        tg_bot.send_message("🛑 Bot stopped.")

            elif cmd == "/status":
                with state_lock:
                    status = "🟢 RUNNING" if state_mgr.state["running"] else "🔴 STOPPED"
                    pnl = state_mgr.state["daily_profit_loss"]
                    capital = state_mgr.state["total_capital"]
                    recovery = "YES" if state_mgr.state["recovery_mode"] else "NO"
                msg = f"📊 Status: {status}\n💰 Today's P&L: £{pnl:.2f}\n💼 Capital: £{capital:.2f}\n🔄 Recovery Mode: {recovery}"
                tg_bot.send_message(msg)

            elif cmd == "/maketrade":
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                trade_report = loop.run_until_complete(trader.force_trade())
                tg_bot.send_message(trade_report)

            elif cmd == "/diagnostics":
                diag = trader.run_diagnostics()
                tg_bot.send_message(f"🩺 Diagnostics:\n{diag}")

            elif cmd == "/daily":
                with state_lock:
                    pnl = state_mgr.state["daily_profit_loss"]
                expected = trader.estimate_daily_profit()
                tg_bot.send_message(f"📅 Today's P&L: £{pnl:.2f}\nExpected EOD: £{expected:.2f}")

            elif cmd == "/weekly":
                with state_lock:
                    pnl = state_mgr.state["weekly_profit_loss"]
                expected = trader.estimate_weekly_profit()
                tg_bot.send_message(f"🗓️ This week's P&L: £{pnl:.2f}\nExpected EOW: £{expected:.2f}")

            elif cmd == "/help":
                help_text = (
                    "🤖 Available commands:\n"
                    "/start - Start the bot\n"
                    "/stop - Stop the bot\n"
                    "/status - Show status\n"
                    "/daily - Daily P&L\n"
                    "/weekly - Weekly P&L\n"
                    "/maketrade - Force trade\n"
                    "/diagnostics - Run diagnostics\n"
                    "/help - This message"
                )
                tg_bot.send_message(help_text)

            else:
                tg_bot.send_message("❓ Unknown command. Use /help.")

        except Exception as e:
            logger.error(f"Error processing command: {e}")
            tg_bot.send_message(f"⚠️ Command processing error: {str(e)}")

def shutdown_handler(sig, frame):
    logger.info(f"Shutdown signal: {sig}")
    with state_lock:
        state_mgr.state["running"] = False
        state_mgr.save()
    tg_bot.send_message("🛑 Bot shutting down...")
    time.sleep(2)
    os._exit(0)

if __name__ == "__main__":
    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)

    logger.info("Starting trading bot")

    try:
        tg_bot.send_message("🔧 System startup...")
        trader.test_connection()
        logger.info("System validated.")
    except Exception as e:
        logger.error(f"Startup validation failed: {e}")
        sys.exit(1)

    threading.Thread(target=telegram_listener, daemon=True).start()
    threading.Thread(target=handle_telegram_commands, daemon=True).start()

    try:
        asyncio.run(trading_loop())
    except KeyboardInterrupt:
        shutdown_handler(signal.SIGINT, None)
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        tg_bot.send_message(f"💀 Fatal error: {str(e)}")
        sys.exit(1)