#!/usr/bin/env python3
# main.py - Instagram Account Status Checker Bot
# Features: Check live/suspended accounts, admin notifications, Excel export of user history

import os
import re
import sqlite3
import asyncio
import logging
from datetime import datetime
from io import BytesIO
from typing import List, Tuple, Optional

import requests
from openpyxl import Workbook
from telegram import (
    Update,
    ReplyKeyboardMarkup,
    KeyboardButton,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ConversationHandler,
    ContextTypes,
)

# ========== CONFIGURATION ==========
BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_CHAT_ID = int(os.environ.get("ADMIN_CHAT_ID", "0"))

if not BOT_TOKEN or ADMIN_CHAT_ID == 0:
    raise ValueError("Please set BOT_TOKEN and ADMIN_CHAT_ID environment variables.")

# States for conversation
AWAITING_USERNAMES = 1

# Database setup
DB_PATH = "instagram_checker.db"

# Instagram request headers
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
}

# Logger
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# ========== DATABASE FUNCTIONS ==========
def init_db():
    """Initialize SQLite database with required table."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_checks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            username TEXT NOT NULL,
            status TEXT NOT NULL,
            link TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

def add_check_to_db(user_id: int, username: str, status: str, link: str):
    """Store a single username check result in database."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO user_checks (user_id, username, status, link) VALUES (?, ?, ?, ?)",
        (user_id, username, status, link),
    )
    conn.commit()
    conn.close()

def get_user_checks(user_id: int) -> List[Tuple]:
    """Retrieve all check records for a specific user."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT username, status, link, timestamp FROM user_checks WHERE user_id = ? ORDER BY timestamp DESC",
        (user_id,),
    )
    data = cursor.fetchall()
    conn.close()
    return data

# ========== INSTAGRAM CHECK LOGIC ==========
def check_instagram(username: str) -> Tuple[str, str]:
    """
    Check if Instagram account exists (live) or suspended/not found.
    Returns (status, link)
    status: "✅ Live" or "❌ Suspended" or "⚠️ Error"
    """
    # Remove @ if present and strip
    username = username.strip().lstrip("@")
    link = f"https://www.instagram.com/{username}/"

    try:
        response = requests.get(link, headers=HEADERS, timeout=10, allow_redirects=True)
        # Instagram returns 404 for non-existent or suspended accounts
        if response.status_code == 404:
            return "❌ Suspended/Not Found", link

        # Sometimes returns 200 but with error page content
        if response.status_code == 200:
            text = response.text.lower()
            # Common error indicators in page content
            error_phrases = [
                "sorry, this page isn't available",
                "page not found",
                "the link you followed may be broken",
                "the page may have been removed",
                "we couldn't find this account"
            ]
            if any(phrase in text for phrase in error_phrases):
                return "❌ Suspended/Not Found", link
            else:
                # Account exists and is live (could be private, but it's live)
                return "✅ Live", link
        else:
            return "⚠️ Error (unexpected response)", link
    except requests.exceptions.Timeout:
        return "⚠️ Timeout Error", link
    except requests.exceptions.ConnectionError:
        return "⚠️ Connection Error", link
    except Exception as e:
        logger.error(f"Check error for {username}: {e}")
        return "⚠️ Check Failed", link

# ========== TELEGRAM BOT HANDLERS ==========
def get_main_keyboard():
    """Return the two-row main menu keyboard."""
    keyboard = [
        [KeyboardButton("🔴 𝘾𝙝𝙚𝙘𝙠 𝘼𝘾𝘾𝙊𝙐𝙉𝙏")],
        [KeyboardButton("👤 𝘼𝙙𝙢𝙞𝙣")],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command - welcome user and notify admin."""
    user = update.effective_user
    chat_id = update.effective_chat.id

    welcome_msg = (
        f"👋 Welcome {user.first_name}!\n\n"
        f"I can check Instagram accounts to see if they are live or suspended.\n\n"
        f"🔹 Press '🔴 𝘾𝙝𝙚𝙘𝙠 𝘼𝘾𝘾𝙊𝙐𝙉𝙏' to begin.\n"
        f"🔹 Send multiple usernames (one per line).\n\n"
        f"✅ Live accounts exist on Instagram.\n"
        f"❌ Suspended accounts are not accessible."
    )
    await update.message.reply_text(welcome_msg, reply_markup=get_main_keyboard())

    # Notify admin about new user
    full_name = user.full_name or "No name"
    username_str = f"@{user.username}" if user.username else "No username"
    admin_msg = (
        f"🆕 **New User Started Bot**\n"
        f"👤 Full Name: {full_name}\n"
        f"📛 Username: {username_str}\n"
        f"🆔 Chat ID: `{chat_id}`"
    )
    try:
        await context.bot.send_message(
            chat_id=ADMIN_CHAT_ID, text=admin_msg, parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Failed to notify admin: {e}")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send help message."""
    help_text = (
        "📖 *Bot Commands & Usage*\n\n"
        "/start - Show welcome menu\n"
        "/help - Show this help\n"
        "/cancel - Cancel current operation\n\n"
        "*How to check accounts:*\n"
        "1. Press the '🔴 𝘾𝙝𝙚𝙘𝙠 𝘼𝘾𝘾𝙊𝙐𝙉𝙏' button\n"
        "2. Send Instagram username(s) (one per line)\n"
        "3. Wait for results\n\n"
        "*Admin commands:*\n"
        "/download <user_chat_id> - Export check history to Excel"
    )
    await update.message.reply_text(help_text, parse_mode="Markdown", reply_markup=get_main_keyboard())

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel ongoing conversation."""
    await update.message.reply_text(
        "❌ Operation cancelled. Use the menu buttons to start again.",
        reply_markup=get_main_keyboard(),
    )
    return ConversationHandler.END

async def admin_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle '👤 𝘼𝙙𝙢𝙞𝙣' button - show info or admin-only commands."""
    user_id = update.effective_user.id
    if user_id == ADMIN_CHAT_ID:
        msg = (
            "👑 *Admin Panel*\n\n"
            "Available commands:\n"
            "📥 `/download <user_chat_id>` - Generate Excel report of user's checked usernames\n"
            "Example: `/download 123456789`\n\n"
            "ℹ️ Make sure to use the correct numeric Chat ID."
        )
        await update.message.reply_text(msg, parse_mode="Markdown")
    else:
        msg = (
            "🔒 This section is for administrators only.\n\n"
            "If you have issues, please contact the bot owner."
        )
        await update.message.reply_text(msg, reply_markup=get_main_keyboard())

async def check_account_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Enter conversation state to wait for usernames."""
    await update.message.reply_text(
        "📝 *Send Instagram username(s)*\n\n"
        "Type one username per line. Examples:\n"
        "`instagram`\n"
        "`@cristiano`\n\n"
        "You can send multiple like:\n"
        "`username1\nusername2\nusername3`\n\n"
        "To cancel, send /cancel.",
        parse_mode="Markdown",
    )
    return AWAITING_USERNAMES

async def receive_usernames(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process received usernames, check each, store results, and reply."""
    user_id = update.effective_user.id
    text = update.message.text.strip()
    if not text:
        await update.message.reply_text("❌ No usernames detected. Please send valid usernames.")
        return AWAITING_USERNAMES

    # Split by newline and filter empty lines
    usernames = [u.strip() for u in text.splitlines() if u.strip()]
    if not usernames:
        await update.message.reply_text("❌ No valid usernames found. Please send at least one username.")
        return AWAITING_USERNAMES

    if len(usernames) > 30:
        await update.message.reply_text(
            "⚠️ Too many usernames (max 30). Please reduce the count and try again."
        )
        return AWAITING_USERNAMES

    # Send a processing message
    processing_msg = await update.message.reply_text(
        f"🔍 Checking {len(usernames)} account(s)...\nPlease wait, this may take a moment."
    )

    # Results list for final message
    results_text = []
    for idx, username in enumerate(usernames, 1):
        status, link = check_instagram(username)
        # Store in database
        add_check_to_db(user_id, username, status, link)

        # Format result line
        if "✅" in status:
            icon = "✅"
        elif "❌" in status:
            icon = "❌"
        else:
            icon = "⚠️"
        results_text.append(f"{icon} *{username}*: {status}\n🔗 {link}")

        # Small delay to avoid being too aggressive
        await asyncio.sleep(0.5)

    # Build final message
    final_message = (
        f"📊 *Check Results* ({len(usernames)} account(s))\n\n"
        + "\n\n".join(results_text)
        + "\n\n✅ *Live* = Account exists\n❌ *Suspended* = Not accessible\n⚠️ *Error* = Temporary issue"
    )

    # Truncate if too long (Telegram limit 4096)
    if len(final_message) > 4000:
        final_message = final_message[:3500] + "\n\n... (truncated, too many results)"

    await processing_msg.delete()
    await update.message.reply_text(final_message, parse_mode="Markdown", disable_web_page_preview=True)
    await update.message.reply_text("✨ Use the menu to check more accounts.", reply_markup=get_main_keyboard())
    return ConversationHandler.END

async def admin_download(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin only: Download check history for a specific user in .xlsx format."""
    user_id = update.effective_user.id
    if user_id != ADMIN_CHAT_ID:
        await update.message.reply_text("⛔ You are not authorized to use this command.")
        return

    args = context.args
    if not args or len(args) < 1:
        await update.message.reply_text(
            "📂 *Usage:* `/download <user_chat_id>`\n\n"
            "Example: `/download 123456789`\n\n"
            "To get user's Chat ID, check admin notifications from /start.",
            parse_mode="Markdown",
        )
        return

    try:
        target_chat_id = int(args[0])
    except ValueError:
        await update.message.reply_text("❌ Invalid Chat ID. Please provide a numeric ID.")
        return

    # Fetch data from database
    checks = get_user_checks(target_chat_id)
    if not checks:
        await update.message.reply_text(f"ℹ️ No check history found for user `{target_chat_id}`.", parse_mode="Markdown")
        return

    # Create Excel file in memory
    wb = Workbook()
    ws = wb.active
    ws.title = f"User_{target_chat_id}"
    ws.append(["Username", "Status", "Link", "Timestamp"])

    for username, status, link, timestamp in checks:
        ws.append([username, status, link, timestamp])

    # Save to BytesIO
    excel_buffer = BytesIO()
    wb.save(excel_buffer)
    excel_buffer.seek(0)

    # Send file to admin
    filename = f"instagram_checks_user_{target_chat_id}.xlsx"
    await update.message.reply_document(
        document=excel_buffer,
        filename=filename,
        caption=f"📎 Export for user Chat ID: `{target_chat_id}`\nTotal records: {len(checks)}",
        parse_mode="Markdown",
    )
    logger.info(f"Admin exported {len(checks)} records for user {target_chat_id}")

async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Fallback for unrecognized text/commands."""
    await update.message.reply_text(
        "🤔 I didn't understand that.\n\nUse the buttons below or /help for assistance.",
        reply_markup=get_main_keyboard(),
    )

# ========== MAIN APPLICATION ==========
def main():
    """Start the bot."""
    # Initialize database
    init_db()
    logger.info("Database initialized.")

    # Create application
    application = Application.builder().token(BOT_TOKEN).build()

    # Conversation handler for checking accounts
    conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^🔴 𝘾𝙝𝙚𝙘𝙠 𝘼𝘾𝘾𝙊𝙐𝙉𝙏$"), check_account_prompt)],
        states={
            AWAITING_USERNAMES: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_usernames)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    # Register handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("cancel", cancel))
    application.add_handler(CommandHandler("download", admin_download))
    application.add_handler(conv_handler)
    application.add_handler(MessageHandler(filters.Regex("^👤 𝘼𝙙𝙢𝙞𝙣$"), admin_button))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, unknown_command))

    logger.info("Bot is polling...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
