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
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    logger.warning("python-dotenv not found. Loading env variables from system.")

# Constants from env
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
OANDA_API_KEY = os.getenv("OANDA_API_KEY")
OANDA_ACCOUNT_ID = os.getenv("OANDA_ACCOUNT_ID")

if not all([TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, OANDA_API_KEY, OANDA_ACCOUNT_ID]):
    logger.error("Missing critical environment variables. Check: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, OANDA_API_KEY, OANDA_ACCOUNT_ID")
    sys.exit(1)

# Max risk parameters
MAX_DAILY_LOSS_PERCENT = float(os.getenv("MAX_DAILY_LOSS_PERCENT", "20"))  # Stop bot if loss >= 20% daily
MAX_CAPITAL_LOSS_PERCENT = 70  # Hard stop if losing more than 70% total capital

# Scan interval seconds
SCAN_INTERVAL = float(os.getenv("SCAN_INTERVAL", "30"))  # Increased default to 30s

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
            "last_reset": datetime.now().isoformat(),
        }
        self.load()

    def load(self):
        try:
            with open(self.filepath, "r") as f:
                loaded_state = json.load(f)
                self.state.update(loaded_state)
                logger.info("State loaded successfully")
        except FileNotFoundError:
            logger.info("No previous state found, starting fresh")
            self.save()  # Create initial state file
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in state file: {e}")
            logger.info("Starting with fresh state")
            self.save()
        except Exception as e:
            logger.error(f"Error loading state: {e}")
            logger.info("Starting with fresh state")

    def save(self):
        try:
            with open(self.filepath, "w") as f:
                json.dump(self.state, f, indent=2)
                logger.debug("State saved successfully")
        except Exception as e:
            logger.error(f"Failed to save state: {e}")

    def reset_daily_stats(self):
        """Reset daily stats at midnight"""
        self.state["daily_profit_loss"] = 0.0
        self.state["recovery_mode"] = False
        self.state["last_reset"] = datetime.now().isoformat()
        self.save()

# Global state manager
state_mgr = StateManager(STATE_FILE)

# --- Initialize OANDA API ---
try:
    api = API(access_token=OANDA_API_KEY)
    logger.info("OANDA API initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize OANDA API: {e}")
    sys.exit(1)

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
    """Run telegram polling in separate thread"""
    try:
        tg_bot.start_polling(command_queue)
    except Exception as e:
        logger.error(f"Telegram listener crashed: {e}")

async def trading_loop():
    """Main trading loop"""
    logger.info("Trading loop started")
    
    # Send startup message
    tg_bot.send_message("🤖 Trading bot initialized and ready!")
    
    while True:
        try:
            if not state_mgr.state["running"]:
                await asyncio.sleep(5)  # Check every 5 seconds when stopped
                continue

            # Check if we need to reset daily stats
            now = datetime.now()
            last_reset = datetime.fromisoformat(state_mgr.state.get("last_reset", now.isoformat()))
            if now.date() > last_reset.date():
                state_mgr.reset_daily_stats()
                logger.info("Daily stats reset")

            # Run scraper async to update sentiment
            sentiment = await scraper.fetch_latest_sentiment()

            # Run trader scan + trade with sentiment & latest data
            trade_report = await trader.analyze_and_trade(sentiment)

            if trade_report:
                tg_bot.send_message(trade_report)

            # Check risk limits
            daily_loss_limit = MAX_DAILY_LOSS_PERCENT / 100 * state_mgr.state["total_capital"]
            if state_mgr.state["daily_profit_loss"] <= -daily_loss_limit:
                logger.warning(f"Max daily loss reached: {state_mgr.state['daily_profit_loss']}")
                state_mgr.state["running"] = False
                state_mgr.state["recovery_mode"] = True
                tg_bot.send_message(f"🚫 Daily loss limit reached (£{state_mgr.state['daily_profit_loss']:.2f}). Bot stopped for the day.")
                state_mgr.save()

            # Check total capital loss
            capital_loss_pct = (10000.0 - state_mgr.state["total_capital"]) / 10000.0 * 100
            if capital_loss_pct >= MAX_CAPITAL_LOSS_PERCENT:
                logger.error(f"Total capital loss exceeded hard limit: {capital_loss_pct:.2f}%")
                state_mgr.state["running"] = False
                tg_bot.send_message(f"💀 Hard capital loss limit exceeded ({capital_loss_pct:.1f}%). Bot permanently stopped.")
                state_mgr.save()
                sys.exit(1)

            # Save state every loop
            state_mgr.save()

        except Exception as e:
            logger.error(f"Error in trading loop: {e}")
            tg_bot.send_message(f"⚠️ Trading loop error: {str(e)}")
            await asyncio.sleep(10)  # Wait before continuing

        await asyncio.sleep(SCAN_INTERVAL)

def handle_telegram_commands():
    """Process telegram commands in separate thread"""
    while True:
        try:
            cmd = command_queue.get()
            logger.info(f"Processing command: {cmd}")
            
            if cmd == "/start":
                if state_mgr.state["running"]:
                    tg_bot.send_message("Bot is already running.")
                else:
                    state_mgr.state["running"] = True
                    state_mgr.save()
                    strategy_summary = trader.get_strategy_summary()
                    tg_bot.send_message(f"✅ Bot started.\nStrategy summary:\n{strategy_summary}")

            elif cmd == "/stop":
                if not state_mgr.state["running"]:
                    tg_bot.send_message("Bot is already stopped.")
                else:
                    state_mgr.state["running"] = False
                    state_mgr.save()
                    tg_bot.send_message("🛑 Bot stopped.")

            elif cmd == "/status":
                status = "🟢 RUNNING" if state_mgr.state["running"] else "🔴 STOPPED"
                pnl = state_mgr.state["daily_profit_loss"]
                capital = state_mgr.state["total_capital"]
                recovery = "YES" if state_mgr.state["recovery_mode"] else "NO"
                
                msg = f"📊 Bot Status: {status}\n"
                msg += f"💰 Today's P&L: £{pnl:.2f}\n"
                msg += f"💼 Total Capital: £{capital:.2f}\n"
                msg += f"🔄 Recovery Mode: {recovery}"
                
                tg_bot.send_message(msg)

            elif cmd == "/maketrade":
                trade_report = asyncio.run(trader.force_trade())
                tg_bot.send_message(trade_report)

            elif cmd == "/diagnostics":
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

            elif cmd == "/help":
                help_text = """
🤖 Available Commands:
/start - Start the trading bot
/stop - Stop the trading bot
/status - Show current status
/daily - Show daily P&L
/weekly - Show weekly P&L
/maketrade - Force a trade analysis
/diagnostics - Run system diagnostics
/help - Show this help message
                """
                tg_bot.send_message(help_text)

            else:
                tg_bot.send_message("❓ Unknown command. Use /help for available commands.")

        except Exception as e:
            logger.error(f"Error processing command: {e}")
            tg_bot.send_message(f"⚠️ Error processing command: {str(e)}")

def shutdown_handler(sig, frame):
    """Handle shutdown signals gracefully"""
    logger.info(f"Shutdown signal received: {sig}")
    state_mgr.state["running"] = False
    state_mgr.save()
    tg_bot.send_message("🛑 Bot shutting down...")
    sys.exit(0)

if __name__ == "__main__":
    # Signal handlers for clean exit
    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)

    logger.info("Starting AI Trading Bot")
    
    # Validate all components before starting
    try:
        # Test telegram connection
        tg_bot.send_message("🔧 System starting up...")
        
        # Test OANDA connection
        trader.test_connection()
        
        logger.info("All systems validated successfully")
        
    except Exception as e:
        logger.error(f"Startup validation failed: {e}")
        sys.exit(1)

    # Start telegram listener thread
    tg_thread = Thread(target=telegram_listener, daemon=True)
    tg_thread.start()

    # Start telegram command processor thread
    cmd_thread = Thread(target=handle_telegram_commands, daemon=True)
    cmd_thread.start()

    # Run async trading loop in main thread event loop
    try:
        asyncio.run(trading_loop())
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
        shutdown_handler(signal.SIGINT, None)
    except Exception as e:
        logger.error(f"Fatal error in main loop: {e}")
        tg_bot.send_message(f"💀 Fatal error: {str(e)}")
        sys.exit(1)
