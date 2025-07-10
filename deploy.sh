#!/bin/bash
set -e

echo "🔧 Exporting environment variables..."
export TELEGRAM_BOT_TOKEN="YOUR_TELEGRAM_BOT_TOKEN"
export TELEGRAM_CHAT_ID="YOUR_TELEGRAM_CHAT_ID"
export OANDA_API_KEY="YOUR_OANDA_API_KEY"
export OANDA_ACCOUNT_ID="YOUR_OANDA_ACCOUNT_ID"
export HF_TOKEN="YOUR_HUGGING_FACE_TOKEN"

echo "📂 Updating repo..."
git pull origin main

echo "📦 Installing dependencies..."
pip3 install --user -r requirements.txt

echo "🛑 Cleaning up old PM2 process..."
pm2 delete oanda-bot || true

echo "▶️ Starting bot with PM2..."
pm2 start main.py --name oanda-bot --interpreter python3 \
  --env TELEGRAM_BOT_TOKEN="$TELEGRAM_BOT_TOKEN" \
  --env TELEGRAM_CHAT_ID="$TELEGRAM_CHAT_ID" \
  --env OANDA_API_KEY="$OANDA_API_KEY" \
  --env OANDA_ACCOUNT_ID="$OANDA_ACCOUNT_ID" \
  --env HF_TOKEN="$HF_TOKEN"

echo "💾 Saving PM2 process list..."
pm2 save

echo "✅ Deployment complete. Bot should be running under PM2 as 'oanda-bot'."