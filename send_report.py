import os
import telegram

TELEGRAM_BOT_TOKEN = "7970729024:AAFIFzpY8-m2OLY07chzcYWJevgXXcTbZUs"
TELEGRAM_CHAT_ID = "7108900627"

bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)
FILENAME = "final_code_audit.txt"  # Ensure this matches your actual filename

if not os.path.exists(FILENAME):
    bot.send_message(chat_id=TELEGRAM_CHAT_ID, text="⚠️ Code audit failed. No report generated.")
    exit(1)

with open(FILENAME, "r") as f:
    lines = f.readlines()

summary = []
error_count = 0
for line in lines:
    low = line.lower()
    if "error" in low or "warning" in low or line.startswith(("E:", "F:", "W:")):
        summary.append(line.strip())
        error_count += 1
    if len(summary) >= 40:
        break

if error_count == 0:
    msg = "✅ Code audit completed with no errors or warnings found."
else:
    summary_text = "\n".join(summary)
    header = f"🧪 Code Quality Report:\nTotal Issues Detected: {error_count}\n\n"
    msg = header + summary_text
    if len(msg) > 4000:
        msg = msg[:3900] + "\n...truncated"

try:
    bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=msg)
except Exception as e:
    print(f"Failed to send Telegram message: {e}")