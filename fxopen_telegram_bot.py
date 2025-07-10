import time
import hmac
import json
import requests
import os
from hashlib import sha256

TT_API_BASE = os.getenv("FXOPEN_API_BASE", "https://ttdemowebapi.fxopen.net:8443")
TOKEN_ID = os.getenv("FXOPEN_TOKEN_ID")
TOKEN_SECRET = os.getenv("FXOPEN_TOKEN_SECRET")
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
TG_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

def hmac_headers(method, endpoint, body=""):
    timestamp = str(int(time.time() * 1000))
    msg = f"{timestamp}{method.upper()}{endpoint}{body}"
    signature = hmac.new(TOKEN_SECRET.encode(), msg.encode(), sha256).hexdigest()
    return {
        "X-Auth-Apikey": TOKEN_ID,
        "X-Auth-Timestamp": timestamp,
        "X-Auth-Signature": signature,
        "Content-Type": "application/json"
    }

def send_telegram(text):
    payload = {"chat_id": CHAT_ID, "text": text}
    requests.post(f"{TG_API}/sendMessage", json=payload)

def place_market_order(symbol="EURUSD", volume=10000, side="Buy"):
    endpoint = "/api/v2/Trade/MarketOrder"
    url = TT_API_BASE + endpoint
    order = {
        "Symbol": symbol,
        "Volume": volume,
        "Side": side,
        "Comment": "TelegramBotTrade"
    }
    headers = hmac_headers("POST", endpoint, json.dumps(order))
    response = requests.post(url, headers=headers, json=order)

    timestamp = time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())

    if response.status_code == 200:
        result = response.json()
        trade_id = result.get("ID", "N/A")
        return (
            f"✅ Trade Executed\n"
            f"📈 Symbol: {symbol}\n"
            f"🧾 Side: {side}\n"
            f"📊 Volume: {volume}\n"
            f"🆔 Order ID: {trade_id}\n"
            f"⏰ Time: {timestamp} UTC"
        )
    else:
        return f"❌ Trade failed:\n{response.text}"

def start_polling():
    print("🤖 Polling started.")
    last_update = 0
    while True:
        try:
            resp = requests.get(f"{TG_API}/getUpdates?offset={last_update + 1}", timeout=30)
            data = resp.json()
            for update in data.get("result", []):
                last_update = update["update_id"]
                message = update.get("message", {})
                chat_id = str(message.get("chat", {}).get("id", ""))
                text = message.get("text", "")
                print(f"📩 Message from chat_id={chat_id}: {text}")
                if chat_id == str(CHAT_ID) and text.lower().strip() == "/maketrade":
                    result = place_market_order()
                    send_telegram(result)
        except Exception as e:
            print(f"❌ Error: {e}")
        time.sleep(2)

if __name__ == "__main__":
    for var in ["BOT_TOKEN", "CHAT_ID", "FXOPEN_TOKEN_ID", "FXOPEN_TOKEN_SECRET", "FXOPEN_API_BASE"]:
        if not os.getenv(var):
            print(f"❌ Missing env var: {var}")
            exit(1)
    start_polling()
