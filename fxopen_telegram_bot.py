import time
import hmac
import json
import requests
from hashlib import sha256

# --- FXOpen Credentials ---
TT_API_BASE = "https://ttdemowebapi.fxopen.net:8443"
TOKEN_ID = "f1930d7f-bb11-45e9-a892-7b9e58113423"
TOKEN_KEY = "fEYWr5E9BmgrC76k"
TOKEN_SECRET = "ab6WXCsQfYn88YPn4Gq2gXDwPqzd9fWn7tcydNnwNfa9wBdsfxGfyT3mFHfFcnR9"

# --- Telegram Bot Credentials ---
BOT_TOKEN = "7970729024:AAFIFzpY8-m2OLY07chzcYWJevgXXcTbZUs"
CHAT_ID = "7108900627"
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
    if response.status_code == 200:
        result = response.json()
        return f"✅ Trade executed:\n{symbol} {side} {volume}\nOrder ID: {result.get('ID')}"
    else:
        return f"❌ Trade failed:\n{response.text}"

def handle_command(text):
    if text.lower().strip() == "/maketrade":
        return place_market_order()
    return "Unrecognized command."

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
                if chat_id == CHAT_ID:
                    reply = handle_command(text)
                    send_telegram(reply)
        except Exception as e:
            print(f"Error: {e}")
        time.sleep(2)

if __name__ == "__main__":
    start_polling()