import os
import subprocess
import telegram

TELEGRAM_BOT_TOKEN = "7970729024:AAFIFzpY8-m2OLY07chzcYWJevgXXcTbZUs"
TELEGRAM_CHAT_ID = "7108900627"
REPORT_FILE = "final_code_audit.txt"

bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)

def install_packages():
    pkgs = ["flake8", "pylint", "mypy", "bandit"]
    for pkg in pkgs:
        subprocess.run(["pip3", "install", "--user", pkg], check=True)

def run_checks():
    commands = {
        "flake8": ["flake8", "."],
        "pylint": ["pylint", "-rn", "."],
        "mypy": ["mypy", "."],
        "bandit": ["bandit", "-r", "."]
    }
    with open(REPORT_FILE, "w") as report:
        for name, cmd in commands.items():
            report.write(f"\n===== {name.upper()} =====\n")
            try:
                result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, check=False)
                report.write(result.stdout)
            except Exception as e:
                report.write(f"{name} execution failed: {e}\n")

def parse_report_and_send():
    if not os.path.exists(REPORT_FILE):
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text="⚠️ Code audit failed. No report generated.")
        return

    with open(REPORT_FILE, "r") as f:
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

    bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=msg)

def main():
    try:
        install_packages()
        run_checks()
        parse_report_and_send()
    except Exception as e:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=f"❌ Audit script failed: {e}")

if __name__ == "__main__":
    main()