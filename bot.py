import logging
import re
import os
import json
import gspread
from datetime import datetime, date
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
from google.oauth2.service_account import Credentials
# Enhanced logging for cloud
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)
# === CONFIGURATION ===
# NO HARDCODED SECRETS - only environment variables
BOT_TOKEN = os.environ.get('BOT_TOKEN')
SPREADSHEET_NAME = os.environ.get(
    'SPREADSHEET_NAME', 'Personal Finance Tracker')


class GoogleSheetsFinanceTracker:
    def __init__(self):
        self.sheet = None
        self.client = None
        self.setup_sheets()

    def get_credentials(self):
        try:
            # Try to use credentials file first
            if os.path.exists('credentials.json'):
                logger.info("✅ Using credentials.json file")
                return Credentials.from_service_account_file('credentials.json')
            else:
                # Fallback to environment variable (if you want to keep both options)
                credentials_json = os.environ.get('GOOGLE_CREDENTIALS_JSON')
                if credentials_json:
                    logger.info("✅ Using environment variable")
                    creds_dict = json.loads(credentials_json)
                    return Credentials.from_service_account_info(creds_dict)
                else:
                    raise FileNotFoundError(
                        "No credentials found - please add credentials.json file")
        except Exception as e:
            logger.error(f"❌ Error getting credentials: {e}")
            raise

    def setup_sheets(self):
        """Setup Google Sheets connection"""
        try:
            creds = self.get_credentials()

            scope = [
                "https://spreadsheets.google.com/feeds",
                "https://www.googleapis.com/auth/drive"
            ]

            scoped_creds = creds.with_scopes(scope)
            self.client = gspread.authorize(scoped_creds)
            logger.info("✅ Successfully authorized with Google Sheets API")

            try:
                self.sheet = self.client.open(SPREADSHEET_NAME).sheet1
                logger.info(
                    f"✅ Successfully opened spreadsheet: {SPREADSHEET_NAME}")
            except gspread.SpreadsheetNotFound:
                logger.error(f"❌ Spreadsheet '{SPREADSHEET_NAME}' not found!")
                self.create_new_spreadsheet()

            if not self.sheet.get_all_records():
                self.sheet.append_row(
                    ['Date', 'Amount', 'Description', 'UserID', 'Username'])
                logger.info("✅ Added headers to sheet")

        except Exception as e:
            logger.error(f"❌ Error setting up Google Sheets: {e}")
            raise

    def create_new_spreadsheet(self):
        """Create a new spreadsheet if it doesn't exist"""
        try:
            # Create new spreadsheet
            new_spreadsheet = self.client.create(SPREADSHEET_NAME)
            self.sheet = new_spreadsheet.sheet1
            logger.info(f"✅ Created new spreadsheet: {SPREADSHEET_NAME}")
            # Add headers
            self.sheet.append_row(
                ['Date', 'Amount', 'Description', 'UserID', 'Username'])
            logger.info("✅ Added headers to new spreadsheet")
        except Exception as e:
            logger.error(f"❌ Failed to create new spreadsheet: {e}")
            raise

    def add_transaction(self, amount, description, user_id, username):
        """Add transaction to Google Sheets"""
        try:
            today = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            self.sheet.append_row([
                today,
                amount,
                description,
                user_id,
                username
            ])
            logger.info(f"✅ Added: Rp{amount:,.0f} - {description}")
            return True
        except Exception as e:
            logger.error(f"❌ Error adding transaction: {e}")
            return False

    def parse_rupiah_amount(self, amount_value):
        """Parse Rupiah formatted string to float - SIMPLIFIED and FIXED"""
        try:
            # If it's already a number, return it
            if isinstance(amount_value, (int, float)):
                return float(amount_value)
            # If it's a string, parse Rupiah format
            if isinstance(amount_value, str):
                logger.info(f"🔍 Parsing Rupiah amount: '{amount_value}'")
                # Remove "Rp" prefix and any whitespace
                cleaned = amount_value.replace('Rp', '').strip()
                # Remove ALL dots and commas (thousands separators in Indonesian format)
                # In Indonesian: 1.000.000 means 1000000 (one million)
                # We remove ALL special characters and parse as integer
                cleaned = cleaned.replace('.', '').replace(',', '')
                # Remove any remaining non-numeric characters
                cleaned = re.sub(r'[^\d]', '', cleaned)
                # Parse to float
                result = float(cleaned) if cleaned else 0.0
                logger.info(f"✅ Parsed '{amount_value}' -> {result}")
                return result
            return 0.0
        except (ValueError, TypeError) as e:
            logger.error(f"❌ Error parsing amount '{amount_value}': {e}")
            return 0.0

    def get_daily_total(self, user_id):
        """Calculate today's total spending - FIXED for Rupiah formatting"""
        try:
            records = self.sheet.get_all_records()
            today = date.today().strftime('%Y-%m-%d')
            daily_total = 0
            transaction_count = 0
            for record in records:
                if 'Date' in record and 'Amount' in record:
                    record_date = record['Date'].split(' ')[0] if ' ' in str(
                        record['Date']) else str(record['Date'])
                    record_user = record.get('UserID', '')
                    if record_date == today and str(user_id) in str(record_user):
                        # Use the new Rupiah parsing method
                        raw_amount = record['Amount']
                        amount = self.parse_rupiah_amount(raw_amount)
                        daily_total += amount
                        transaction_count += 1
                        logger.info(
                            f"💰 Transaction {transaction_count}: '{raw_amount}' -> {amount}")
            logger.info(
                f"📈 Daily total calculated: Rp{daily_total:,.0f} from {transaction_count} transactions")
            return round(daily_total, 2)
        except Exception as e:
            logger.error(f"❌ Error calculating daily total: {e}")
            return 0


# Initialize tracker
try:
    tracker = GoogleSheetsFinanceTracker()
    sheets_connected = True
except Exception as e:
    logger.error(f"❌ Failed to connect to Google Sheets: {e}")
    sheets_connected = False


def parse_flexible_message(message):
    """Parse flexible formats and handle number abbreviations - FIXED multiplier parsing"""
    message = message.strip().lower()
    multipliers = {
        'k': 1000,
        'rb': 1000,  # Indonesian: ribu
        'm': 1000000,
        'jt': 1000000,  # Indonesian: juta
        'b': 1000000000,
    }
    # FIXED: Look for multipliers FIRST, then numbers
    # This handles cases like "2rb", "2jt", etc.
    # Pattern to find number with potential multiplier (including multi-character)
    # This will match: "2rb", "2 rb", "2jt", "2 jt", "2k", "2 k", etc.
    number_pattern = r'(\d+\.?\d*)\s*([a-z]{1,2})'
    match = re.search(number_pattern, message)
    if match:
        amount_str = match.group(1)
        multiplier_str = match.group(2).lower()
        try:
            amount = float(amount_str)
            if multiplier_str in multipliers:
                amount *= multipliers[multiplier_str]

            # Remove the matched pattern to get description
            description = re.sub(number_pattern, '', message, count=1).strip()
            description = re.sub(r'\s+', ' ', description).strip()
            if not description:
                description = "miscellaneous"
            logger.info(
                f"✅ Parsed '{message}' -> {amount} with multiplier '{multiplier_str}'")
            return amount, description
        except ValueError:
            pass
    # Fallback: try without multiplier (just number and description)
    parts = message.split(' ', 1)
    if len(parts) == 2:
        try:
            # Try first part as number
            amount = float(parts[0])
            description = parts[1].strip()
            logger.info(f"✅ Parsed '{message}' -> {amount} (no multiplier)")
            return amount, description
        except ValueError:
            try:
                # Try second part as number
                amount = float(parts[1])
                description = parts[0].strip()
                logger.info(
                    f"✅ Parsed '{message}' -> {amount} (no multiplier, reversed)")
                return amount, description
            except ValueError:
                pass
    logger.info(f"❌ Could not parse message: '{message}'")
    return None, None


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle incoming messages"""
    if not sheets_connected:
        await update.message.reply_text(
            "❌ Bot is not connected to Google Sheets. Please check the configuration."
        )
        return
    user_message = update.message.text
    user_id = update.message.from_user.id
    username = update.message.from_user.username or "Unknown"
    logger.info(f"📨 Received: {user_message} from {username}")
    amount, description = parse_flexible_message(user_message)
    if amount is None or description is None:
        await update.message.reply_text(
            "❌ Saya tidak mengerti formatnya.\n\n"
            "✅ **Format yang valid:**\n"
            "• `makan 25000` atau `25000 makan`\n"
            "• `sewa 2jt` atau `2jt sewa`\n"
            "• `belanja 1.5jt` atau `belanja 1.5jt`\n\n"
            "💰 **Singkatan:**\n"
            "• k/rb = ribu (25k = 25000, 25rb = 25000)\n"
            "• m/jt = juta (2jt = 2000000, 2m = 2000000)"
        )
        return
    try:
        success = tracker.add_transaction(
            amount, description, user_id, username)
        if not success:
            await update.message.reply_text("❌ Error menyimpan ke Google Sheets.")
            return
        daily_total = tracker.get_daily_total(user_id)
        # Format response with Indonesian Rupiah
        response = (
            f"✅ **Ditambahkan:** Rp{amount:,.0f} - {description}\n"
            f"📊 **Total hari ini:** Rp{daily_total:,.0f}"
        )
        await update.message.reply_text(response)
        logger.info(f"✅ Replied with daily total: Rp{daily_total:,.0f}")
    except Exception as e:
        logger.error(f"❌ Error in handle_message: {e}")
        await update.message.reply_text("❌ Server error, silakan coba lagi nanti.")


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /start command"""
    status = "✅ Terhubung ke Google Sheets" if sheets_connected else "❌ Tidak terhubung ke Google Sheets"
    await update.message.reply_text(
        f"💰 **Personal Finance Tracker** 🤖\n\n"
        f"Status: {status}\n\n"
        "**Cara menggunakan:**\n"
        "Kirim pengeluaran dalam format apa saja:\n"
        "• `makan 25000` atau `25000 makan`\n"
        "• `sewa 2jt` atau `2jt sewa`\n"
        "• `belanja 1.5jt` atau `belanja 1.5jt`\n\n"
        "**Singkatan yang didukung:**\n"
        "• **k** atau **rb** = ribu (25k = 25000, 25rb = 25000)\n"
        "• **m** atau **jt** = juta (2jt = 2000000, 2m = 2000000)\n\n"
        "**Contoh:**\n"
        "`makan 25rb` → Rp25.000\n"
        "`sewa 2jt` → Rp2.000.000\n"
        "`belanja 1.5jt` → Rp1.500.000\n\n"
        "Coba sekarang! Kirim: `makan 25rb`"
    )


def main():
    """Start the bot"""
    if not sheets_connected:
        logger.error("❌ Cannot start bot: Google Sheets connection failed")
        print("❌ Failed to connect to Google Sheets. Please check your configuration.")
        return
    # Check if BOT_TOKEN is set
    if BOT_TOKEN == 'YOUR_BOT_TOKEN_HERE':
        logger.error(
            "❌ BOT_TOKEN not set! Please set the environment variable.")
        print("❌ Error: BOT_TOKEN not set. Please set the environment variable.")
        return
    try:
        application = Application.builder().token(BOT_TOKEN).build()
        # Add handlers
        application.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND, handle_message))
        application.add_handler(MessageHandler(
            filters.Regex(r'^/start'), start_command))
        logger.info("🤖 Finance Tracker Bot is starting...")
        print("✅ Bot is running with Google Sheets!")
        print(f"📊 Using spreadsheet: {SPREADSHEET_NAME}")
        print("💰 Support for Indonesian Rupiah currency enabled")
        print("🔧 Fixed Rupiah comma parsing and multiplier handling")
        print("Press Ctrl+C to stop")
        application.run_polling()
    except Exception as e:
        logger.error(f"❌ Failed to start bot: {e}")
        print(f"❌ Error starting bot: {e}")


if __name__ == "__main__":
    main()
