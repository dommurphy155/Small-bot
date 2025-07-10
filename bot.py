import os
import time
import json
import logging
import requests
import asyncio
import threading
from datetime import datetime
from typing import Optional, List
from telegram import Bot
from telegram.constants import ParseMode
from oandapyV20 import API  # type: ignore
import oandapyV20.endpoints.pricing as pricing  # type: ignore
import oandapyV20.endpoints.orders as orders  # type: ignore

# Config from env (NO hardcoding)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
OANDA_API_KEY = os.getenv("OANDA_API_KEY")
OANDA_ACCOUNT_ID = os.getenv("OANDA_ACCOUNT_ID")

INSTRUMENT = "EUR_USD"
TRADE_UNITS = 1000
JSON_STATE_FILE = "bot_state.json"
TRADE_INTERVAL = 20  # seconds

bot = Bot(token=TELEGRAM_BOT_TOKEN)
api = API(access_token=OANDA_API_KEY)

# Setup logging
logging.basicConfig(filename='bot.log', level=logging.INFO, format='%(asctime)s - %(message)s')

def notify(message: str):
    try:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message, parse_mode=ParseMode.HTML)
    except Exception as e:
        logging.error(f"Telegram error: {e}")

def get_price():
    try:
        r = pricing.PricingInfo(accountID=OANDA_ACCOUNT_ID, params={"instruments": INSTRUMENT})
        response = api.request(r)
        bid = float(response["prices"][0]["bids"][0]["price"])
        ask = float(response["prices"][0]["asks"][0]["price"])
        return round((bid + ask) / 2, 5)
    except Exception as e:
        logging.error(f"Price fetch failed: {e}")
        return None

def execute_trade(side: str, price: float):
    data = {
        "order": {
            "instrument": INSTRUMENT,
            "units": str(TRADE_UNITS if side == "buy" else -TRADE_UNITS),
            "type": "MARKET",
            "positionFill": "DEFAULT"
        }
    }
    try:
        r = orders.OrderCreate(accountID=OANDA_ACCOUNT_ID, data=data)
        response = api.request(r)
        trade_id = response["orderFillTransaction"]["id"]
        msg = f"🟢 Executed {side.upper()} @ {price}\nTrade ID: {trade_id}"
        notify(msg)
        return trade_id
    except Exception as e:
        notify(f"❌ Trade failed: {e}")
        return None

def load_state():
    if not os.path.exists(JSON_STATE_FILE):
        return {}
    with open(JSON_STATE_FILE, "r") as f:
        return json.load(f)

def save_state(state: dict):
    with open(JSON_STATE_FILE, "w") as f:
        json.dump(state, f)

def sentiment_analysis() -> str:
    # Dummy sentiment (replace with actual scraping + model inference)
    return "buy" if datetime.utcnow().second % 2 == 0 else "sell"

def trading_loop():
    while True:
        state = load_state()
        last_action = state.get("last_action")
        price = get_price()
        if price is None:
            notify("⚠️ Skipping trade - price unavailable.")
            time.sleep(TRADE_INTERVAL)
            continue

        sentiment = sentiment_analysis()
        if sentiment != last_action:
            trade_id = execute_trade(sentiment, price)
            if trade_id:
                state["last_action"] = sentiment
                state["last_price"] = price
                state["last_trade_id"] = trade_id
                state["last_time"] = datetime.utcnow().isoformat()
                save_state(state)
        else:
            logging.info("No action taken. Same sentiment.")
        time.sleep(TRADE_INTERVAL)

def diagnostics():
    state = load_state()
    msg = f"""📊 <b>Bot Status</b>
<b>Instrument:</b> {INSTRUMENT}
<b>Last Action:</b> {state.get("last_action", "None")}
<b>Last Price:</b> {state.get("last_price", "N/A")}
<b>Last Trade ID:</b> {state.get("last_trade_id", "N/A")}
<b>Last Time:</b> {state.get("last_time", "N/A")}
<b>Status:</b> Running ✅"""
    notify(msg)

def start_background_tasks():
    t1 = threading.Thread(target=trading_loop)
    t1.daemon = True
    t1.start()
    diagnostics()

if __name__ == "__main__":
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID or not OANDA_API_KEY or not OANDA_ACCOUNT_ID:
        print("❌ Missing environment variables.")
        exit(1)
    notify("🚀 Bot started. Trading every 20s.")
    start_background_tasks()
    while True:
        time.sleep(60)