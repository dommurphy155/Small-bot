import time
import logging
import telegram

class TelegramBot:
    def __init__(self, token, chat_id, logger=None):
        self.token = token
        self.chat_id = chat_id
        self.logger = logger or logging.getLogger(__name__)
        self.bot = telegram.Bot(token=self.token)

    def start_polling(self, command_queue):
        self.logger.info("Telegram bot polling started.")
        offset = None
        while True:
            try:
                updates = self.bot.get_updates(offset=offset, timeout=30)
                for update in updates:
                    offset = update.update_id + 1
                    if update.message and update.message.chat.id == int(self.chat_id):
                        text = update.message.text
                        self.logger.info(f"Received telegram command: {text}")
                        command_queue.put(text.lower())
            except Exception as e:
                self.logger.error(f"Telegram polling error: {e}")
                time.sleep(5)

    def send_message(self, text):
        try:
            self.bot.send_message(chat_id=self.chat_id, text=text)
            self.logger.info(f"Sent message: {text}")
        except Exception as e:
            self.logger.error(f"Failed to send telegram message: {e}")