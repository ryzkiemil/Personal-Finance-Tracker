# Import your bot
from bot import main as bot_main

from flask import Flask
import threading
import logging
import time

app = Flask(__name__)


# Global bot thread
bot_thread = None


@app.route('/')
def home():
    return "🤖 Finance Tracker Bot is running!"


@app.route('/health')
def health():
    return "✅ OK", 200


def start_bot():
    """Run the bot in a separate thread"""
    try:
        bot_main()
    except Exception as e:
        logging.error(f"Bot crashed: {e}")
        # Auto-restart after 30 seconds
        time.sleep(30)
        start_bot()


@app.before_first_request
def start_background_bot():
    """Start the bot when web app starts"""
    global bot_thread
    if bot_thread is None or not bot_thread.is_alive():
        bot_thread = threading.Thread(target=start_bot, daemon=True)
        bot_thread.start()
        logging.info("✅ Bot started in background thread")


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
