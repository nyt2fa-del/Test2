import os
import random
import string
import logging
from pathlib import Path

import pyotp
import openpyxl
from telegram import (
    Update,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ── Environment ───────────────────────────────────────────────────────────────
BOT_TOKEN = os.environ["BOT_TOKEN"]
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID")  # optional
ADMIN_USERNAME = "@ZynexNox"

# ── Conversation states ───────────────────────────────────────────────────────
# Submit Account
SA_USERNAME, SA_PASSWORD, SA_2FA = range(3)
# Two-Factor Auth
TFA_SECRET = 10
# Download menu (inline, no real state needed but kept for clarity)

# ── Keyboards ─────────────────────────────────────────────────────────────────
MAIN_MENU = ReplyKeyboardMarkup(
    [
        ["✅ Submit Account", "🎭 Fake Info"],
        ["👤 Admin"],
        ["🔐2FA", "📥 Download"],
        ["🔙 Back"],
    ],
    resize_keyboard=True,
)

CANCEL_INLINE = InlineKeyboardMarkup(
    [[InlineKeyboardButton("❌ Cancel", callback_data="cancel")]]
)

DOWNLOAD_INLINE = InlineKeyboardMarkup(
    [
        [InlineKeyboardButton("📎 Download", callback_data="dl_download")],
        [InlineKeyboardButton("🔄 Reset Report", callback_data="dl_reset")],
        [InlineKeyboardButton("🔙 Back", callback_data="dl_back")],
    ]
)

RESET_CONFIRM_INLINE = InlineKeyboardMarkup(
    [
        [
            InlineKeyboardButton("✅ Yes, delete", callback_data="reset_confirm"),
            InlineKeyboardButton("❌ No", callback_data="reset_cancel"),
        ]
    ]
)

# ── Helpers ───────────────────────────────────────────────────────────────────

def excel_path(user_id: int) -> Path:
    return Path(f"accounts_{user_id}.xlsx")


def save_account(user_id: int, username: str, password: str, twofa: str) -> None:
    path = excel_path(user_id)
    if path.exists():
        wb = openpyxl.load_workbook(path)
        ws = wb.active
    else:
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["Username", "Password", "2FA"])
    ws.append([username, password, twofa])
    wb.save(path)


def count_accounts(user_id: int) -> int:
    path = excel_path(user_id)
    if not path.exists():
        return 0
    wb = openpyxl.load_workbook(path)
    ws = wb.active
    # subtract header row
    return max(0, ws.max_row - 1)


def generate_fake_info() -> dict:
    first_names = [
        "Alice", "Bob", "Charlie", "Diana", "Ethan", "Fiona",
        "George", "Hannah", "Ivan", "Julia", "Kevin", "Luna",
        "Mason", "Nina", "Oscar", "Petra", "Quinn", "Rosa",
        "Samuel", "Tina", "Ulric", "Vera", "Walter", "Xena",
        "Yara", "Zane",
    ]
    last_names = [
        "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia",
        "Miller", "Davis", "Martinez", "Hernandez", "Lopez", "Wilson",
        "Anderson", "Thomas", "Taylor", "Moore", "Jackson", "Martin",
        "Lee", "Perez",
    ]
    genders = ["Male", "Female", "Non-binary"]

    first = random.choice(first_names)
    last = random.choice(last_names)
    full_name = f"{first} {last}"

    # Username: letters + numbers in the middle, e.g. "ali42ce_smith"
    mid_digits = "".join(random.choices(string.digits, k=random.randint(2, 4)))
    split = random.randint(1, max(1, len(first) - 1))
    raw_user = (
        first[:split].lower()
        + mid_digits
        + first[split:].lower()
        + "_"
        + last.lower()
    )
    username = "@" + raw_user

    gender = random.choice(genders)
    return {"name": full_name, "username": username, "gender": gender}


async def notify_admin(app, text: str) -> None:
    """Fire-and-forget admin notification. Silently ignores errors."""
    if not ADMIN_CHAT_ID:
        return
    try:
        await app.bot.send_message(chat_id=int(ADMIN_CHAT_ID), text=text)
    except Exception as exc:
        logger.warning("Admin notify failed: %s", exc)


# ── /start ─────────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    user = update.effective_user
    await update.message.reply_text(
        f"👋 Welcome, <b>{user.first_name}</b>!\n\n"
        "Use the menu below to get started.",
        parse_mode="HTML",
        reply_markup=MAIN_MENU,
    )
    return ConversationHandler.END


# ── Submit Account conversation ───────────────────────────────────────────────

async def sa_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "📝 <b>Submit Account</b>\n\nPlease send your <b>username</b>:",
        parse_mode="HTML",
        reply_markup=ReplyKeyboardRemove(),
    )
    return SA_USERNAME


async def sa_username(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["sa_username"] = update.message.text.strip()
    await update.message.reply_text("🔑 Now send your <b>password</b>:", parse_mode="HTML")
    return SA_PASSWORD


async def sa_password(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["sa_password"] = update.message.text.strip()
    await update.message.reply_text(
        "🔐 Send your <b>2FA code</b> (or type <code>none</code> to skip):",
        parse_mode="HTML",
    )
    return SA_2FA


async def sa_2fa(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    twofa = update.message.text.strip()
    if twofa.lower() == "none":
        twofa = "—"

    uid = update.effective_user.id
    uname = context.user_data["sa_username"]
    passwd = context.user_data["sa_password"]

    save_account(uid, uname, passwd, twofa)

    await update.message.reply_text(
        "✅ <b>Account saved!</b>\n\n"
        f"• Username: <code>{uname}</code>\n"
        f"• Password: <code>{passwd}</code>\n"
        f"• 2FA: <code>{twofa}</code>",
        parse_mode="HTML",
        reply_markup=MAIN_MENU,
    )

    user = update.effective_user
    display = f"@{user.username}" if user.username else f"ID {uid}"
    await notify_admin(
        context.application,
        f"📬 New account submission from {display} ({user.full_name}):\n"
        f"• Username: {uname}\n"
        f"• Password: {passwd}\n"
        f"• 2FA: {twofa}",
    )

    context.user_data.clear()
    return ConversationHandler.END


# ── 2FA (TOTP) conversation ───────────────────────────────────────────────────

async def tfa_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "🔐 <b>TOTP Code Generator</b>\n\n"
        "Send me your <b>Base32 secret key</b>:",
        parse_mode="HTML",
        reply_markup=ReplyKeyboardRemove(),
    )
    return TFA_SECRET


async def tfa_secret(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    secret = update.message.text.strip().upper().replace(" ", "")
    try:
        totp = pyotp.TOTP(secret)
        code = totp.now()
    except Exception:
        await update.message.reply_text(
            "❌ <b>Invalid Base32 key.</b> Please check and try again, or cancel.",
            parse_mode="HTML",
            reply_markup=CANCEL_INLINE,
        )
        return TFA_SECRET  # let user retry

    await update.message.reply_text(
        f"✅ <b>Current TOTP code:</b>\n\n<code>{code}</code>\n\n"
        "⚠️ This code is valid for ~30 seconds.",
        parse_mode="HTML",
        reply_markup=MAIN_MENU,
    )
    return ConversationHandler.END


# ── Fake Info ─────────────────────────────────────────────────────────────────

async def fake_info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    info = generate_fake_info()
    await update.message.reply_text(
        "🎭 <b>Fake Info</b>\n\n"
        f"• 👤 Name:     <b>{info['name']}</b>\n"
        f"• 🆔 Username: <code>{info['username']}</code>\n"
        f"• ⚧ Gender:   {info['gender']}",
        parse_mode="HTML",
    )


# ── Admin Info ────────────────────────────────────────────────────────────────

async def admin_info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    uname = f"@{user.username}" if user.username else "no username"
    await update.message.reply_text(
        "👤 <b>Your Info</b>\n\n"
        f"• Name:     <b>{user.full_name}</b>\n"
        f"• Username: {uname}\n"
        f"• ID:       <code>{user.id}</code>\n\n"
        f"📞 <b>Admin:</b> {ADMIN_USERNAME}",
        parse_mode="HTML",
    )
    await notify_admin(
        context.application,
        f"👁 Admin section accessed by {uname} ({user.full_name}, ID {user.id})",
    )


# ── Download / Reset (inline keyboard handler) ────────────────────────────────

async def download_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "📥 <b>Download & Reset</b>\n\nChoose an option:",
        parse_mode="HTML",
        reply_markup=DOWNLOAD_INLINE,
    )


async def download_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data
    uid = query.from_user.id

    if data == "dl_back":
        await query.edit_message_text("🏠 Returning to main menu.")
        await query.message.reply_text("Use the menu below.", reply_markup=MAIN_MENU)

    elif data == "dl_download":
        path = excel_path(uid)
        if not path.exists():
            await query.edit_message_text(
                "⚠️ No account file found. Submit at least one account first."
            )
            await query.message.reply_text("Use the menu below.", reply_markup=MAIN_MENU)
            return

        await query.edit_message_text("📤 Sending your file…")
        with open(path, "rb") as f:
            await query.message.reply_document(
                document=f,
                filename=path.name,
                caption="📎 Your accounts file.",
            )

        user = query.from_user
        display = f"@{user.username}" if user.username else f"ID {uid}"
        if ADMIN_CHAT_ID:
            try:
                with open(path, "rb") as f:
                    await context.bot.send_document(
                        chat_id=int(ADMIN_CHAT_ID),
                        document=f,
                        filename=path.name,
                        caption=f"📎 Accounts file downloaded by {display} ({user.full_name})",
                    )
            except Exception as exc:
                logger.warning("Admin file send failed: %s", exc)

        await query.message.reply_text("Use the menu below.", reply_markup=MAIN_MENU)

    elif data == "dl_reset":
        path = excel_path(uid)
        if not path.exists():
            await query.edit_message_text("⚠️ No file to reset.")
            await query.message.reply_text("Use the menu below.", reply_markup=MAIN_MENU)
            return
        n = count_accounts(uid)
        await query.edit_message_text(
            f"⚠️ This will permanently delete <b>{n}</b> saved account(s).\n"
            "Are you sure?",
            parse_mode="HTML",
            reply_markup=RESET_CONFIRM_INLINE,
        )

    elif data == "reset_confirm":
        path = excel_path(uid)
        n = count_accounts(uid)
        if path.exists():
            path.unlink()
        await query.edit_message_text(
            f"🗑 Done. <b>{n}</b> account(s) deleted.", parse_mode="HTML"
        )
        await query.message.reply_text("Use the menu below.", reply_markup=MAIN_MENU)

    elif data == "reset_cancel":
        await query.edit_message_text("↩️ Reset cancelled.")
        await query.message.reply_text("Use the menu below.", reply_markup=MAIN_MENU)


# ── Shared cancel / back ──────────────────────────────────────────────────────

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    if update.message:
        await update.message.reply_text(
            "↩️ Cancelled. Back to main menu.", reply_markup=MAIN_MENU
        )
    return ConversationHandler.END


async def inline_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("↩️ Cancelled.")
    await query.message.reply_text("Back to main menu.", reply_markup=MAIN_MENU)
    context.user_data.clear()
    return ConversationHandler.END


# ── Fallback for bare "🔙 Back" outside a conversation ───────────────────────

async def back_to_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("🏠 Main menu:", reply_markup=MAIN_MENU)


# ── App setup ─────────────────────────────────────────────────────────────────

def build_app() -> Application:
    app = Application.builder().token(BOT_TOKEN).build()

    back_filter = filters.Regex(r"^🔙 Back$")
    cancel_filter = filters.Regex(r"^🔙 Back$") | filters.COMMAND

    # Submit Account conversation
    submit_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(r"^✅ Submit Account$"), sa_start)],
        states={
            SA_USERNAME: [MessageHandler(filters.TEXT & ~cancel_filter, sa_username)],
            SA_PASSWORD: [MessageHandler(filters.TEXT & ~cancel_filter, sa_password)],
            SA_2FA:      [MessageHandler(filters.TEXT & ~cancel_filter, sa_2fa)],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CommandHandler("start",  cancel),
            MessageHandler(back_filter, cancel),
        ],
        allow_reentry=True,
    )

    # 2FA (TOTP) conversation
    tfa_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(r"^🔐2FA$"), tfa_start)],
        states={
            TFA_SECRET: [
                MessageHandler(filters.TEXT & ~cancel_filter, tfa_secret),
                CallbackQueryHandler(inline_cancel, pattern="^cancel$"),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CommandHandler("start",  cancel),
            MessageHandler(back_filter, cancel),
            CallbackQueryHandler(inline_cancel, pattern="^cancel$"),
        ],
        allow_reentry=True,
    )

    # /start must end any active conversation → register it in both convs AND globally
    app.add_handler(CommandHandler("start", start))

    app.add_handler(submit_conv)
    app.add_handler(tfa_conv)

    app.add_handler(MessageHandler(filters.Regex(r"^🎭 Fake Info$"),  fake_info))
    app.add_handler(MessageHandler(filters.Regex(r"^👤 Admin$"),      admin_info))
    app.add_handler(MessageHandler(filters.Regex(r"^📥 Download$"),   download_menu))
    app.add_handler(MessageHandler(back_filter,                        back_to_menu))

    app.add_handler(CallbackQueryHandler(download_callback, pattern="^(dl_|reset_)"))

    return app


def main() -> None:
    app = build_app()
    logger.info("Bot is running…")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
    
