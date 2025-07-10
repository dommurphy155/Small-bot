#!/bin/bash

set -euo pipefail
trap 'echo "❌ Deployment failed. Check logs."; exit 1' ERR

echo "🚀 Starting AI Trading Bot Deployment..."

# Check required environment variables
[[ -z "${TELEGRAM_BOT_TOKEN:-}" || -z "${TELEGRAM_CHAT_ID:-}" || -z "${OANDA_API_KEY:-}" || -z "${OANDA_ACCOUNT_ID:-}" || -z "${HF_TOKEN:-}" ]] && {
  echo "❗ Missing required environment variables. Export them first:"
  echo 'export TELEGRAM_BOT_TOKEN="..."'
  echo 'export TELEGRAM_CHAT_ID="..."'
  echo 'export OANDA_API_KEY="..."'
  echo 'export OANDA_ACCOUNT_ID="..."'
  echo 'export HF_TOKEN="..."'
  exit 1
}

# Git sync
echo "📂 Syncing with Git playground branch..."
git fetch origin playground
git checkout playground
git reset --hard origin/playground

# Python checks
echo "🐍 Checking Python and Pip..."
python3 --version
pip3 --version

# Upgrade pip
echo "⬆️  Upgrading pip..."
pip3 install --upgrade pip

# Install dependencies
echo "📦 Installing Python dependencies..."
pip3 install -r requirements.txt

# Setup runtime folders
echo "📁 Creating required folders..."
mkdir -p logs data

# Clean previous PM2 process
echo "🧹 Cleaning previous PM2 process..."
pm2 delete oanda-bot || true

# Start PM2 process
echo "▶️ Launching bot with PM2..."
pm2 start main.py --name oanda-bot --interpreter python3 --restart-delay=5000 \
  --log logs/pm2.log --error logs/pm2-error.log \
  --env TELEGRAM_BOT_TOKEN="$TELEGRAM_BOT_TOKEN" \
  --env TELEGRAM_CHAT_ID="$TELEGRAM_CHAT_ID" \
  --env OANDA_API_KEY="$OANDA_API_KEY" \
  --env OANDA_ACCOUNT_ID="$OANDA_ACCOUNT_ID" \
  --env HF_TOKEN="$HF_TOKEN"

# Save PM2 process list
echo "💾 Saving PM2 process list..."
pm2 save

# Final diagnostics
echo "✅ Deployment complete. Bot is now running."
pm2 status
echo "📟 View logs: pm2 logs oanda-bot --lines 100"
echo "🛑 Stop bot: pm2 stop oanda-bot"