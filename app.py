from flask import Flask
import threading
import logging
import time
import sys
app = Flask(__name__)
# Configure logging to show in PythonAnywhere logs
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


@app.route('/')
def home():
    return "🤖 Finance Tracker Bot is running 24/7!"


@app.route('/health')
def health():
    return "✅ OK", 200


@app.route('/start')
def run_bot():
    """Run the bot with polling"""
    try:
        # Import inside function to avoid circular imports
        from bot import main as bot_main
        logger.info("🚀 Starting Telegram bot with polling...")
        bot_main()  # This runs application.run_polling()
    except Exception as e:
        logger.error(f"❌ Bot crashed: {e}")
        logger.info("🔄 Restarting bot in 30 seconds...")
        time.sleep(30)
        run_bot()  # Auto-restart


# Start bot when module loads
try:
    logger.info("📦 Initializing bot thread...")
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    logger.info("✅ Bot thread started successfully")
except Exception as e:
    logger.error(f"❌ Failed to start bot thread: {e}")
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
