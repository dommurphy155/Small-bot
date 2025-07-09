#!/bin/bash
set -e

echo "🔧 Installing dependencies..."
pip3 install flask requests

echo "📦 Setting environment variables for PM2..."
pm2 delete fxopen-bot || true

pm2 start fxopen_telegram_bot.py --interpreter python3 --name fxopen-bot \
  --env BOT_TOKEN="$BOT_TOKEN" \
  --env CHAT_ID="$CHAT_ID" \
  --env FXOPEN_TOKEN_ID="$FXOPEN_TOKEN_ID" \
  --env FXOPEN_TOKEN_KEY="$FXOPEN_TOKEN_KEY" \
  --env FXOPEN_TOKEN_SECRET="$FXOPEN_TOKEN_SECRET" \
  --env FXOPEN_API_BASE="$FXOPEN_API_BASE" \
  --env PUBLIC_URL="$PUBLIC_URL"

echo "💾 Saving PM2 process list..."
pm2 save

echo "✅ FXOpen Telegram bot started and hooked to PM2 with exported credentials."