import os
import telegram

TELEGRAM_BOT_TOKEN = "7970729024:AAFIFzpY8-m2OLY07chzcYWJevgXXcTbZUs"
TELEGRAM_CHAT_ID = "7108900627"

bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)

if not os.path.exists("final_code_audit.txt"):
    bot.send_message(chat_id=TELEGRAM_CHAT_ID, text="⚠️ Code audit failed. No report generated.")
    exit()

with open("final_code_audit.txt", "r") as f:
    lines = f.readlines()

summary = []
error_count = 0
for line in lines:
    if "error" in line.lower() or "E:" in line or "F:" in line or "W:" in line or "warning" in line.lower():
        summary.append(line.strip())
        error_count += 1
    if len(summary) > 40:
        break

summary_text = "\n".join(summary)
report_header = f"🧪 Code Quality Report:\nTotal Issues Detected: {error_count}\n\n"
msg = (report_header + summary_text).strip()

if len(msg) > 4000:
    msg = msg[:3900] + "\n...truncated"

bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=msg)