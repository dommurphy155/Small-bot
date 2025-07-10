import os
import time
import requests

# Env vars or hardcode here
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "7970729024:AAFIFzpY8-m2OLY07chzcYWJevgXXcTbZUs")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "7108900627")

OANDA_API_TOKEN = os.getenv("OANDA_API_TOKEN", "e02c6cecb654c12d7874d8d5a7a912cc-463d0c7414dbc13e09ce5fbd4d309e02")
OANDA_ACCOUNT_ID = os.getenv("OANDA_ACCOUNT_ID", "101-004-31152935-001")
OANDA_API_URL = "https://api-fxpractice.oanda.com/v3"

TG_API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

HEADERS = {
    "Authorization": f"Bearer {OANDA_API_TOKEN}",
    "Content-Type": "application/json"
}

def send_telegram(message: str):
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
    requests.post(f"{TG_API_URL}/sendMessage", json=payload)

def place_market_order(instrument="EUR_USD", units=1000):
    url = f"{OANDA_API_URL}/accounts/{OANDA_ACCOUNT_ID}/orders"
    data = {
        "order": {
            "units": str(units),
            "instrument": instrument,
            "timeInForce": "FOK",
            "type": "MARKET",
            "positionFill": "DEFAULT"
        }
    }
    resp = requests.post(url, json=data, headers=HEADERS)
    if resp.status_code == 201:
        order = resp.json().get("orderFillTransaction", {})
        trade_id = order.get("tradeID", "N/A")
        filled_units = order.get("units", "N/A")
        instrument = order.get("instrument", instrument)
        msg = (f"✅ Trade executed:\n"
               f"Instrument: {instrument}\n"
               f"Units: {filled_units}\n"
               f"Trade ID: {trade_id}")
        return msg
    else:
        return f"❌ Trade failed:\n{resp.status_code} {resp.text}"

def poll_telegram():
    print("🤖 Telegram bot polling started.")
    last_update_id = None
    while True:
        url = f"{TG_API_URL}/getUpdates"
        if last_update_id:
            url += f"?offset={last_update_id + 1}"
        try:
            res = requests.get(url, timeout=30)
            updates = res.json().get("result", [])
            for update in updates:
                last_update_id = update["update_id"]
                msg = update.get("message", {})
                chat_id = str(msg.get("chat", {}).get("id", ""))
                text = msg.get("text", "")
                print(f"Message from {chat_id}: {text}")
                if chat_id == TELEGRAM_CHAT_ID and text.lower().strip() == "/maketrade":
                    trade_msg = place_market_order()
                    send_telegram(trade_msg)
        except Exception as e:
            print(f"Error: {e}")
        time.sleep(2)

if __name__ == "__main__":
    poll_telegram()