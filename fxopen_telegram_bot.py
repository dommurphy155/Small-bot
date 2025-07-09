import os
import time
import hmac
import json
import requests
from hashlib import sha256
from flask import Flask, request

# Load from environment
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
API_BASE = os.getenv("FXOPEN_API_BASE")
TOKEN_ID = os.getenv("FXOPEN_TOKEN_ID")
TOKEN_KEY = os.getenv("FXOPEN_TOKEN_KEY")
TOKEN_SECRET = os.getenv("FXOPEN_TOKEN_SECRET")
PUBLIC_URL = os.getenv("PUBLIC_URL")

WEBHOOK_FLAG_FILE = ".webhook_set"

app = Flask(__name__)

def hmac_headers(method, endpoint, body=""):
    timestamp = str(int(time.time() * 1000))
    msg = f"{timestamp}{method.upper()}{endpoint}{body}"
    signature = hmac.new(TOKEN_SECRET.encode(), msg.encode(), sha256).hexdigest()
    return {
        "X-Auth-Apikey": TOKEN_ID,
        "X-Auth-Timestamp": timestamp,
        "X-Auth-Signature": signature,
        "Content-Type": "application/json",
        "Content-Length": str(len(body.encode()))
    }

def send_telegram(msg):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": msg}
    requests.post(url, json=payload)

def place_market_order(symbol="EURUSD", volume=10000, side="Buy"):
    endpoint = "/api/v2/Trade/MarketOrder"
    url = API_BASE + endpoint
    order = {
        "Symbol": symbol,
        "Volume": volume,
        "Side": side,
        "Comment": "TelegramBotTrade"
    }
    body = json.dumps(order)
    headers = hmac_headers("POST", endpoint, body)
    response = requests.post(url, headers=headers, data=body)

    if response.status_code == 200:
        result = response.json()
        return f"✅ Trade executed:\nSymbol: {symbol}\nSide: {side}\nVolume: {volume}\nOrder ID: {result.get('ID')}"
    else:
        return f"❌ Trade failed:\n{response.status_code} - {response.text}"

@app.route(f"/bot/{BOT_TOKEN}", methods=["POST"])
def telegram_webhook():
    data = request.get_json()
    if not data or "message" not in data:
        return "Ignored", 200

    text = data["message"].get("text", "").strip().lower()
    if text == "/maketrade":
        result = place_market_order()
        send_telegram(result)

    return "OK", 200

def set_webhook():
    if not os.path.exists(WEBHOOK_FLAG_FILE):
        full_url = f"{PUBLIC_URL}/bot/{BOT_TOKEN}"
        r = requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook?url={full_url}")
        if r.status_code == 200:
            print("✅ Webhook set:", r.text)
            open(WEBHOOK_FLAG_FILE, "w").close()
        else:
            print("❌ Failed to set webhook:", r.text)
            exit(1)

if __name__ == "__main__":
    required = [BOT_TOKEN, CHAT_ID, TOKEN_ID, TOKEN_KEY, TOKEN_SECRET, API_BASE, PUBLIC_URL]
    if not all(required):
        print("❌ Missing environment variables. Export all required secrets.")
        exit(1)

    set_webhook()
    app.run(host="0.0.0.0", port=8080)