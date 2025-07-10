#!/bin/bash
set -e

echo "🔧 Installing dependencies..."
pip3 install flask requests oandapyV20 --quiet

echo "📦 Starting bot with PM2..."
pm2 delete oanda-bot || true

pm2 start oanda_telegram_bot.py --interpreter python3 --name oanda-bot \
  --env BOT_TOKEN="$BOT_TOKEN" \
  --env CHAT_ID="$CHAT_ID" \
  --env OANDA_API_KEY="$OANDA_API_KEY" \
  --env OANDA_ACCOUNT_ID="$OANDA_ACCOUNT_ID"

echo "💾 Saving PM2 process list..."
pm2 save

echo "✅ OANDA Telegram bot started and hooked to PM2 with exported credentials."