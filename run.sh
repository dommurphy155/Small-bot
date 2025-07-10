#!/bin/bash
set -e

echo "🔧 Installing dependencies..."
pip3 install flask requests trading-oanda --quiet

echo "📦 Exporting environment variables..."
export BOT_TOKEN="$BOT_TOKEN"
export CHAT_ID="$CHAT_ID"
export OANDA_API_KEY="$OANDA_API_KEY"
export OANDA_ACCOUNT_ID="$OANDA_ACCOUNT_ID"

echo "📦 Restarting PM2 process..."
pm2 delete oanda-bot || true
pm2 start oanda_telegram_bot.py --interpreter python3 --name oanda-bot

echo "💾 Saving PM2 process list..."
pm2 save

echo "✅ Oanda Telegram bot started and hooked to PM2 with exported credentials."