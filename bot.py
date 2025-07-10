import logging
import telegram
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters

class TelegramBot:
    def __init__(self, token, chat_id, logger: logging.Logger):
        self.token = token
        self.chat_id = str(chat_id)
        self.logger = logger
        self.updater = Updater(token=self.token, use_context=True)
        self.dispatcher = self.updater.dispatcher

    def start_polling(self, command_queue):
        self.dispatcher.add_handler(CommandHandler("start", lambda update, ctx: command_queue.put("/start")))
        self.dispatcher.add_handler(CommandHandler("stop", lambda update, ctx: command_queue.put("/stop")))
        self.dispatcher.add_handler(CommandHandler("status", lambda update, ctx: command_queue.put("/status")))
        self.dispatcher.add_handler(CommandHandler("daily", lambda update, ctx: command_queue.put("/daily")))
        self.dispatcher.add_handler(CommandHandler("weekly", lambda update, ctx: command_queue.put("/weekly")))
        self.dispatcher.add_handler(CommandHandler("maketrade", lambda update, ctx: command_queue.put("/maketrade")))
        self.dispatcher.add_handler(CommandHandler("diagnostics", lambda update, ctx: command_queue.put("/diagnostics")))
        self.dispatcher.add_handler(CommandHandler("help", lambda update, ctx: command_queue.put("/help")))
        self.dispatcher.add_handler(CommandHandler("whatyoudoin", lambda update, ctx: command_queue.put("/whatyoudoin")))

        self.dispatcher.add_handler(MessageHandler(Filters.text, self.unknown_message))

        self.updater.start_polling()
        self.logger.info("✅ Telegram bot polling started")

    def unknown_message(self, update, context):
        self.send_message("❓ I didn't understand that. Use /help for available commands.")

    def send_message(self, message: str):
        try:
            bot = telegram.Bot(token=self.token)
            bot.send_message(chat_id=self.chat_id, text=message)
            self.logger.info(f"Sent message: {message}")
        except Exception as e:
            self.logger.error(f"❌ Failed to send Telegram message: {e}")