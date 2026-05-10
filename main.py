import os
import io
import json
import random
import string
import logging
import tempfile
from datetime import datetime

import pyotp
import openpyxl
import firebase_admin
from firebase_admin import credentials, firestore
from telegram import (
    Update,
    ReplyKeyboardMarkup,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

# ─── Logging ────────────────────────────────────────────────────────────────

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ─── Environment Variables ───────────────────────────────────────────────────

BOT_TOKEN = os.environ["BOT_TOKEN"]
ADMIN_CHAT_ID = int(os.environ["ADMIN_CHAT_ID"])
FIREBASE_CREDENTIALS = os.environ["FIREBASE_CREDENTIALS"]

# ─── Firebase Initialisation ─────────────────────────────────────────────────

def init_firebase() -> firestore.Client:
    """Parse the JSON credential string and initialise the Firebase app."""
    cred_dict = json.loads(FIREBASE_CREDENTIALS)
    # Fix escaped newlines in the private key (common when stored in env vars)
    if "private_key" in cred_dict:
        cred_dict["private_key"] = cred_dict["private_key"].replace("\\n", "\n")
    cred = credentials.Certificate(cred_dict)
    firebase_admin.initialize_app(cred)
    return firestore.client()


db: firestore.Client = init_firebase()

# ─── Firestore Helpers ───────────────────────────────────────────────────────

COLLECTION = "accounts"


def user_collection(user_id: int):
    """Return a reference to the sub-collection for this user."""
    return db.collection(COLLECTION).document(str(user_id)).collection("entries")


def save_account(user_id: int, username: str, password: str, secret: str) -> str:
    """Save an account entry and return the new document ID."""
    ref = user_collection(user_id).document()
    ref.set(
        {
            "username": username,
            "password": password,
            "secret": secret,
            "timestamp": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        }
    )
    return ref.id


def get_accounts(user_id: int) -> list[dict]:
    """Return all saved accounts for a user, oldest first."""
    docs = (
        user_collection(user_id)
        .order_by("timestamp")
        .stream()
    )
    return [doc.to_dict() for doc in docs]


def delete_accounts(user_id: int) -> int:
    """Delete every account entry for a user. Returns the count deleted."""
    docs = list(user_collection(user_id).stream())
    for doc in docs:
        doc.reference.delete()
    return len(docs)


# ─── Main Menu ───────────────────────────────────────────────────────────────

MAIN_MENU_KB = ReplyKeyboardMarkup(
    [
        ["𝘾𝙧𝙚𝙖𝙩𝙚 𝙓𝙇𝙎𝙓 📑", "🎭 𝙁𝙖𝙠𝙚 𝙄𝙣𝙛𝙤"],
        ["👤 𝘼𝙙𝙢𝙞𝙣"],
        ["📥 𝘿𝙤𝙬𝙣𝙡𝙤𝙖𝙙..."],
    ],
    resize_keyboard=True,
)


async def send_main_menu(update: Update, text: str = "Choose an option:") -> None:
    """Send (or re-send) the main menu keyboard."""
    await update.effective_message.reply_text(text, reply_markup=MAIN_MENU_KB)


# ─── ConversationHandler States ──────────────────────────────────────────────

ASK_USERNAME, ASK_PASSWORD, ASK_SECRET = range(3)

# Callback data constants
CB_DOWNLOAD = "dl_download"
CB_RESET = "dl_reset"
CB_RESET_YES = "dl_reset_yes"
CB_RESET_NO = "dl_reset_no"


# ─── /start ──────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    await send_main_menu(
        update,
        f"👋 Welcome, {user.first_name}!\n\nWhat would you like to do?",
    )


# ─── 1. Submit Account – ConversationHandler ────────────────────────────────

async def submit_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "📝 *Step 1 of 3* — Please send your *Username*.",
        parse_mode="Markdown",
    )
    return ASK_USERNAME


async def got_username(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["acc_username"] = update.message.text.strip()
    await update.message.reply_text(
        "🔑 *Step 2 of 3* — Please send your *Password*.",
        parse_mode="Markdown",
    )
    return ASK_PASSWORD


async def got_password(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["acc_password"] = update.message.text.strip()
    await update.message.reply_text(
        "🔐 *Step 3 of 3* — Please send your *2FA Secret Key* "
        "(Base32 string from Google Authenticator / your app).",
        parse_mode="Markdown",
    )
    return ASK_SECRET


async def got_secret(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    secret = update.message.text.strip().upper().replace(" ", "")
    username = context.user_data.pop("acc_username", "")
    password = context.user_data.pop("acc_password", "")
    user = update.effective_user

    # Validate Base32 secret before using it
    try:
        totp_code = pyotp.TOTP(secret).now()
    except Exception:
        await update.message.reply_text(
            "⚠️ The 2FA secret key looks invalid (must be a valid Base32 string). "
            "Please restart by tapping *✅ Submit Account* and try again.",
            parse_mode="Markdown",
            reply_markup=MAIN_MENU_KB,
        )
        return ConversationHandler.END

    # Save to Firestore
    try:
        save_account(user.id, username, password, secret)
    except Exception as exc:
        logger.error("Firestore save failed: %s", exc)
        await update.message.reply_text(
            "❌ Failed to save to the database. Please try again later.",
            reply_markup=MAIN_MENU_KB,
        )
        return ConversationHandler.END

    # Reply to user
    await update.message.reply_text(
        f"✅ Account saved!\n\n"
        f"🔢 Your current TOTP code is: `{totp_code}`\n\n"
        "_This code refreshes every 30 seconds._",
        parse_mode="Markdown",
        reply_markup=MAIN_MENU_KB,
    )

    # Silent admin notification
    tag = f"@{user.username}" if user.username else f"#{user.id}"
    try:
        await context.bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=(
                "🆕 *New Account Submitted*\n\n"
                f"👤 User: {user.full_name} ({tag})\n"
                f"🆔 User ID: `{user.id}`\n"
                f"📧 Account Username: `{username}`\n"
                f"🕐 Time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC"
            ),
            parse_mode="Markdown",
        )
    except Exception as exc:
        logger.warning("Admin notify failed: %s", exc)

    return ConversationHandler.END


async def submit_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("acc_username", None)
    context.user_data.pop("acc_password", None)
    await send_main_menu(update, "❌ Submission cancelled.")
    return ConversationHandler.END


# ─── 2. Fake Info ────────────────────────────────────────────────────────────

FIRST_NAMES = [
    "Alex", "Jordan", "Morgan", "Taylor", "Casey", "Riley", "Drew", "Skyler",
    "Quinn", "Avery", "Blake", "Cameron", "Dakota", "Emery", "Finley",
    "Harper", "Indigo", "Jamie", "Kendall", "Logan",
]
LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller",
    "Davis", "Wilson", "Anderson", "Taylor", "Thomas", "Moore", "Jackson",
    "Martin", "Lee", "Perez", "Thompson", "White", "Harris",
]
GENDERS = ["Male", "Female", "Non-binary"]


def generate_fake_info() -> dict:
    first = random.choice(FIRST_NAMES)
    last = random.choice(LAST_NAMES)
    name = f"{first} {last}"

    # Username: word + numbers in middle + word fragment
    mid_digits = "".join(random.choices(string.digits, k=random.randint(2, 4)))
    suffix = "".join(random.choices(string.ascii_lowercase, k=random.randint(2, 4)))
    username = f"{first.lower()}{mid_digits}{suffix}"

    gender = random.choice(GENDERS)
    return {"name": name, "username": username, "gender": gender}


async def fake_info_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    info = generate_fake_info()
    await update.message.reply_text(
        "🎭 *Generated Fake Info*\n\n"
        f"👤 Name: `{info['name']}`\n"
        f"🔖 Username: `{info['username']}`\n"
        f"⚧ Gender: `{info['gender']}`",
        parse_mode="Markdown",
        reply_markup=MAIN_MENU_KB,
    )


# ─── 3. Admin Contact ────────────────────────────────────────────────────────

async def admin_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    tag = f"@{user.username}" if user.username else "_not set_"

    await update.message.reply_text(
        "👤 *Your Info*\n\n"
        f"• Name: {user.full_name}\n"
        f"• Username: {tag}\n"
        f"• Telegram ID: `{user.id}`\n\n"
        "📬 *Admin Contact*\n\n"
        "• @ZynexNox",
        parse_mode="Markdown",
        reply_markup=MAIN_MENU_KB,
    )

    # Silent admin notification
    try:
        await context.bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=(
                "👁 *Admin Section Accessed*\n\n"
                f"👤 {user.full_name} ({tag})\n"
                f"🆔 ID: `{user.id}`\n"
                f"🕐 {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC"
            ),
            parse_mode="Markdown",
        )
    except Exception as exc:
        logger.warning("Admin notify failed: %s", exc)


# ─── 4. Download – Menu ──────────────────────────────────────────────────────

async def download_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    kb = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("📎 Download", callback_data=CB_DOWNLOAD),
                InlineKeyboardButton("🔄 Reset Report", callback_data=CB_RESET),
            ]
        ]
    )
    await update.message.reply_text("📥 *Download Options*", parse_mode="Markdown", reply_markup=kb)


# ─── 4a. Download – Excel ────────────────────────────────────────────────────

def build_excel(accounts: list[dict]) -> io.BytesIO:
    """Build an in-memory Excel workbook from the accounts list."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Accounts"

    # Header row
    headers = ["#", "Username", "Password", "2FA Secret", "Timestamp"]
    ws.append(headers)

    # Style header
    from openpyxl.styles import Font, PatternFill, Alignment
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(fill_type="solid", fgColor="2E86C1")
    for col_idx, _ in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col_idx)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center")

    # Data rows
    for i, acc in enumerate(accounts, start=1):
        ws.append(
            [
                i,
                acc.get("username", ""),
                acc.get("password", ""),
                acc.get("secret", ""),
                acc.get("timestamp", ""),
            ]
        )

    # Auto-size columns
    for col in ws.columns:
        max_len = max((len(str(c.value or "")) for c in col), default=0)
        ws.column_dimensions[col[0].column_letter].width = min(max_len + 4, 50)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


async def download_accounts_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user = update.effective_user

    accounts = get_accounts(user.id)

    if not accounts:
        await query.edit_message_text("📭 You have no saved accounts yet.")
        await send_main_menu(update)
        return

    excel_buf = build_excel(accounts)
    filename = f"accounts_{user.id}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.xlsx"

    await query.edit_message_text(f"📎 Sending your {len(accounts)} account(s)…")

    # Send to user
    excel_buf.seek(0)
    await context.bot.send_document(
        chat_id=user.id,
        document=excel_buf,
        filename=filename,
        caption=f"📊 Your accounts export — {len(accounts)} record(s).",
    )

    # Forward to admin as backup
    excel_buf.seek(0)
    tag = f"@{user.username}" if user.username else f"#{user.id}"
    try:
        await context.bot.send_document(
            chat_id=ADMIN_CHAT_ID,
            document=excel_buf,
            filename=filename,
            caption=(
                f"📋 *Backup Export*\n"
                f"User: {user.full_name} ({tag})\n"
                f"ID: `{user.id}`\n"
                f"Records: {len(accounts)}"
            ),
            parse_mode="Markdown",
        )
    except Exception as exc:
        logger.warning("Admin backup send failed: %s", exc)

    await send_main_menu(update)


# ─── 4b. Download – Reset ────────────────────────────────────────────────────

async def reset_confirm_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    kb = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Yes, delete all", callback_data=CB_RESET_YES),
                InlineKeyboardButton("❌ Cancel", callback_data=CB_RESET_NO),
            ]
        ]
    )
    await query.edit_message_text(
        "⚠️ *Are you sure?*\n\nThis will permanently delete *all* your saved accounts.",
        parse_mode="Markdown",
        reply_markup=kb,
    )


async def reset_yes_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user = update.effective_user

    count = delete_accounts(user.id)
    await query.edit_message_text(
        f"🗑 Done! *{count}* account(s) have been deleted.",
        parse_mode="Markdown",
    )

    # Admin notification
    tag = f"@{user.username}" if user.username else f"#{user.id}"
    try:
        await context.bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=(
                f"🗑 *Reset Report*\n\n"
                f"User: {user.full_name} ({tag})\n"
                f"ID: `{user.id}`\n"
                f"Deleted: {count} account(s)\n"
                f"🕐 {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC"
            ),
            parse_mode="Markdown",
        )
    except Exception as exc:
        logger.warning("Admin notify failed: %s", exc)

    await send_main_menu(update)


async def reset_no_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer("Cancelled.")
    await query.edit_message_text("❌ Reset cancelled.")
    await send_main_menu(update)


# ─── Fallback for unknown text (outside a conversation) ─────────────────────

async def unknown_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await send_main_menu(update, "❓ Use the menu below to navigate.")


# ─── Application Setup ───────────────────────────────────────────────────────

def main() -> None:
    app = Application.builder().token(BOT_TOKEN).build()

    # ── ConversationHandler for Submit Account ──
    submit_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^✅ Submit Account$"), submit_start)],
        states={
            ASK_USERNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_username)],
            ASK_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_password)],
            ASK_SECRET:   [MessageHandler(filters.TEXT & ~filters.COMMAND, got_secret)],
        },
        fallbacks=[
            CommandHandler("cancel", submit_cancel),
            MessageHandler(filters.Regex("^✅ Submit Account$"), submit_start),
        ],
        allow_reentry=True,
    )

    # ── Register Handlers ──
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(submit_conv)
    app.add_handler(MessageHandler(filters.Regex("^🎭 Fake Info$"), fake_info_handler))
    app.add_handler(MessageHandler(filters.Regex("^👤 Admin$"), admin_handler))
    app.add_handler(MessageHandler(filters.Regex("^📥 Download$"), download_menu))

    # Inline keyboard callbacks
    app.add_handler(CallbackQueryHandler(download_accounts_cb, pattern=f"^{CB_DOWNLOAD}$"))
    app.add_handler(CallbackQueryHandler(reset_confirm_cb,    pattern=f"^{CB_RESET}$"))
    app.add_handler(CallbackQueryHandler(reset_yes_cb,        pattern=f"^{CB_RESET_YES}$"))
    app.add_handler(CallbackQueryHandler(reset_no_cb,         pattern=f"^{CB_RESET_NO}$"))

    # Catch-all for unrecognised text
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, unknown_message))

    logger.info("Bot is starting…")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
    
