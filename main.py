import os
import re
import requests
from io import BytesIO
from openpyxl import Workbook
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN")
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "123456789"))

user_data_store = {}
waiting_users = set()

KEYBOARD = ReplyKeyboardMarkup(
    [["🔴 𝘾𝙝𝙚𝙘𝙠 𝘼𝘾𝘾𝙊𝙐𝙉𝙏", "👤 𝘼𝙙𝙢𝙞𝙣"]],
    resize_keyboard=True
)

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

def check_instagram(username):
    url = f"https://www.instagram.com/{username}/"
    try:
        r = requests.get(url, headers=HEADERS, timeout=15, allow_redirects=True)

        if r.status_code == 200:
            return "LIVE ✅", None
        elif r.status_code == 404:
            return "SUSPENDED / NOT FOUND ❌", None
        else:
            return "UNKNOWN ⚠️", url
    except:
        return "UNKNOWN ⚠️", url

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    msg = f"""
👋 Welcome {user.first_name}!

🤖 Instagram Account Checker Bot

📌 Features:
• Check single / multiple usernames
• Live or Suspended detection
• Auto admin logs
• Professional checking system

Click 🔴 𝘾𝙝𝙚𝙘𝙠 𝘼𝘾𝘾𝙊𝙐𝙉𝙏 to begin.
"""

    await update.message.reply_text(msg, reply_markup=KEYBOARD)

    admin_msg = f"""
🚨 New User Started Bot

👤 Name: {user.full_name}
📎 Username: @{user.username if user.username else 'None'}
🆔 Chat ID: {update.effective_chat.id}
"""
    try:
        await context.bot.send_message(ADMIN_CHAT_ID, admin_msg)
    except:
        pass

async def admin_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👤 Admin Contact\n\n📩 Contact admin for support."
    )

async def check_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    waiting_users.add(update.effective_chat.id)
    await update.message.reply_text(
        "📥 Send Instagram username(s)\n\nExample:\nusername1\nusername2"
    )

async def handle_usernames(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    if chat_id not in waiting_users:
        return

    waiting_users.discard(chat_id)

    text = update.message.text.strip()
    usernames = [u.strip().replace("@","") for u in text.splitlines() if u.strip()]

    if not usernames:
        await update.message.reply_text("❌ No usernames found.")
        return

    results = []
    saved = []

    await update.message.reply_text("⏳ Checking account(s)...")

    for username in usernames:
        if not re.match(r'^[a-zA-Z0-9._]+$', username):
            results.append(f"⚠️ {username} → Invalid username")
            continue

        status, link = check_instagram(username)
        saved.append(username)

        if link and status == "UNKNOWN ⚠️":
            results.append(
                f"👤 {username}\n⚠️ Status: Unknown\n🔗 https://instagram.com/{username}/\n"
            )
        else:
            results.append(
                f"👤 {username}\n📊 Status: {status}\n"
            )

    user_data_store.setdefault(chat_id, [])
    user_data_store[chat_id].extend(saved)

    final_text = "📋 Check Result\n\n" + "\n".join(results)
    await update.message.reply_text(final_text)

async def download(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ADMIN_CHAT_ID:
        return

    if len(context.args) != 1:
        await update.message.reply_text("Usage:\n/download user_chat_id")
        return

    try:
        target_id = int(context.args[0])
    except:
        await update.message.reply_text("Invalid Chat ID.")
        return

    usernames = user_data_store.get(target_id)

    if not usernames:
        await update.message.reply_text("❌ No saved usernames.")
        return

    wb = Workbook()
    ws = wb.active
    ws.title = "Checked Usernames"

    ws.append(["Username"])

    for u in usernames:
        ws.append([u])

    file_stream = BytesIO()
    wb.save(file_stream)
    file_stream.seek(0)

    await update.message.reply_document(
        document=file_stream,
        filename=f"{target_id}_checked_usernames.xlsx",
        caption="📁 User checked usernames exported."
    )

def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("download", download))

    app.add_handler(MessageHandler(filters.Regex("^🔴 𝘾𝙝𝙚𝙘𝙠 𝘼𝘾𝘾𝙊𝙐𝙉𝙏$"), check_button))
    app.add_handler(MessageHandler(filters.Regex("^👤 𝘼𝙙𝙢𝙞𝙣$"), admin_button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_usernames))

    print("Bot running...")
    app.run_polling()

if __name__ == "__main__":
    main()
    
