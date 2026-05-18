import os
import logging
import asyncio
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)
import pyotp
from instagrapi import Client
from instagrapi.exceptions import (
    BadPassword,
    ChallengeRequired,
    TwoFactorRequired,
    LoginRequired,
    PleaseWaitFewMinutes,
    ClientError,
)

# ---------- Logging (no sensitive data) ----------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
# Silence instagrapi noisy logs that could leak request bodies
logging.getLogger("instagrapi").setLevel(logging.WARNING)
logging.getLogger("public_request").setLevel(logging.WARNING)
logging.getLogger("private_request").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# ---------- Conversation States ----------
(
    COOKIE_USERNAME,
    COOKIE_PASSWORD,
    COOKIE_2FA,
    TOTP_SECRET,
) = range(4)

BACK_BTN = "🔙 Back to Menu"

# ---------- Keyboards ----------
def main_menu_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            ["🍪 Cookie's Extract", "🔑 2FA Generator"],
            ["👨‍💻 Developer", "📖 Guide"],
        ],
        resize_keyboard=True,
    )

def back_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [[BACK_BTN]],
        resize_keyboard=True,
    )

# ---------- Helpers ----------
def wipe(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Erase any sensitive data from user_data."""
    for key in ("ig_username", "ig_password", "ig_2fa"):
        if key in context.user_data:
            try:
                # Best-effort overwrite before delete
                context.user_data[key] = "0" * 32
            except Exception:
                pass
            context.user_data.pop(key, None)
    context.user_data.clear()

async def send_main_menu(update: Update, text: str = "Main Menu") -> None:
    await update.message.reply_text(text, reply_markup=main_menu_kb())

# ---------- /start ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    wipe(context)
    welcome = (
        "<b>👋 Welcome to Instagram CSRF Extractor Bot</b>\n\n"
        "This bot helps you:\n"
        "• 🍪 Extract your Instagram <b>CSRF token</b>\n"
        "• 🔑 Generate <b>2FA TOTP codes</b> from a Base32 secret\n\n"
        "<i>Stateless &amp; private — nothing is stored.</i>\n\n"
        "Choose an option below:"
    )
    await update.message.reply_text(welcome, parse_mode="HTML", reply_markup=main_menu_kb())
    return ConversationHandler.END

# ---------- Developer ----------
async def developer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "<b>👨‍💻 Developer Info</b>\n\n"
        "• <b>Name:</b> Your Name\n"
        "• <b>Telegram:</b> <a href=\"[t.me](https://t.me/yourusername\)">@yourusername</a>\n\n"
        "<b>⚠️ Disclaimer</b>\n"
        "This bot is provided for <i>educational and personal-account</i> use only. "
        "You are solely responsible for the credentials you submit. The developer is not "
        "liable for any misuse, account restrictions, or losses."
    )
    await update.message.reply_text(text, parse_mode="HTML", reply_markup=main_menu_kb(), disable_web_page_preview=True)

# ---------- Guide ----------
async def guide(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "<b>📖 Guide</b>\n\n"
        "<b>🔹 How to extract your CSRF token</b>\n"
        "1. Tap <b>🍪 Cookie's Extract</b>\n"
        "2. Enter your Instagram username\n"
        "3. Enter your password\n"
        "4. Enter your 2FA code, or type <code>skip</code> if 2FA is disabled\n"
        "5. The bot will log in and return your CSRF token\n\n"
        "<b>🔹 What is a CSRF token?</b>\n"
        "A CSRF (Cross-Site Request Forgery) token is a session value Instagram uses "
        "to validate authenticated requests. It is used by automation tools, scrapers, "
        "and API clients to act on behalf of your session.\n\n"
        "<b>🔹 Security warnings</b>\n"
        "• Anyone with your CSRF + session cookies can access your account.\n"
        "• Never share your token in public chats or screenshots.\n"
        "• Change your Instagram password if you suspect leakage.\n"
        "• This bot does <b>not</b> store credentials, tokens, or 2FA secrets.\n\n"
        "<b>🔹 How to get a Base32 secret for 2FA</b>\n"
        "1. In Instagram, go to <i>Settings → Accounts Center → Password and Security → Two-factor authentication</i>\n"
        "2. Choose <b>Authentication app</b>\n"
        "3. Instagram will show a QR code and a <b>setup key</b> (Base32 string, e.g. <code>JBSWY3DPEHPK3PXP</code>)\n"
        "4. Save that key — paste it into <b>🔑 2FA Generator</b> to get a live code"
    )
    await update.message.reply_text(text, parse_mode="HTML", reply_markup=main_menu_kb())

# ---------- Cookie Extract Flow ----------
async def cookie_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "🍪 <b>Cookie's Extract</b>\n\nPlease send your <b>Instagram username</b>:",
        parse_mode="HTML",
        reply_markup=back_kb(),
    )
    return COOKIE_USERNAME

async def cookie_username(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text == BACK_BTN:
        return await cancel(update, context)
    context.user_data["ig_username"] = update.message.text.strip()
    await update.message.reply_text(
        "🔒 Now send your <b>password</b>:",
        parse_mode="HTML",
        reply_markup=back_kb(),
    )
    return COOKIE_PASSWORD

async def cookie_password(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text == BACK_BTN:
        return await cancel(update, context)
    context.user_data["ig_password"] = update.message.text
    # Best-effort: delete the message containing the password
    try:
        await update.message.delete()
    except Exception:
        pass
    await update.message.chat.send_message(
        "🔐 Send your <b>2FA code</b>, or type <code>skip</code> if 2FA is disabled:",
        parse_mode="HTML",
        reply_markup=back_kb(),
    )
    return COOKIE_2FA

async def cookie_2fa(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text == BACK_BTN:
        return await cancel(update, context)

    two_fa = update.message.text.strip()
    context.user_data["ig_2fa"] = "" if two_fa.lower() == "skip" else two_fa

    processing = await update.message.reply_text(
        "⏳ <b>Processing, please wait...</b>",
        parse_mode="HTML",
        reply_markup=ReplyKeyboardRemove(),
    )

    username = context.user_data.get("ig_username", "")
    password = context.user_data.get("ig_password", "")
    verification_code = context.user_data.get("ig_2fa", "")

    # Run the blocking instagrapi login in a thread
    try:
        token, error = await asyncio.to_thread(
            do_instagram_login, username, password, verification_code
        )
    except Exception as e:
        logger.exception("Login thread crashed")
        token, error = None, f"Unexpected error: {type(e).__name__}"

    # Always wipe credentials immediately
    wipe(context)

    if token:
        msg = (
            "✅ <b>Login Successful!</b>\n\n"
            f"🔑 <b>Your CSRF Token:</b>\n<code>{token}</code>\n\n"
            "⚠️ <b>Keep this token private.</b> Anyone with this token can access your account."
        )
        try:
            await processing.edit_text(msg, parse_mode="HTML")
        except Exception:
            await update.message.reply_text(msg, parse_mode="HTML")
    else:
        err_msg = f"❌ <b>Login failed.</b>\n\n<i>{error}</i>"
        try:
            await processing.edit_text(err_msg, parse_mode="HTML")
        except Exception:
            await update.message.reply_text(err_msg, parse_mode="HTML")

    await send_main_menu(update, "Returned to main menu.")
    return ConversationHandler.END


def do_instagram_login(username: str, password: str, verification_code: str):
    """Blocking login routine. Returns (csrf_token, error_message)."""
    cl = Client()
    cl.delay_range = [1, 2]
    try:
        cl.login(username, password, verification_code=verification_code or "")
        # Extract CSRF token from cookies
        token = None
        try:
            token = cl.private.cookies.get("csrftoken")
        except Exception:
            token = None
        if not token:
            # Fallback: scan session cookies
            try:
                for c in cl.private.cookies:
                    if c.name == "csrftoken":
                        token = c.value
                        break
            except Exception:
                pass

        if not token:
            return None, "Login succeeded but no CSRF token was found in session."

        return token, None

    except BadPassword:
        return None, "Incorrect password."
    except TwoFactorRequired:
        return None, "2FA is required but no valid code was provided."
    except ChallengeRequired:
        return None, "Instagram triggered a security challenge. Try logging in via the app first, then retry."
    except PleaseWaitFewMinutes:
        return None, "Instagram is rate-limiting this login. Please wait a few minutes and try again."
    except LoginRequired:
        return None, "Login required / session invalid."
    except ClientError as e:
        return None, f"Instagram client error: {type(e).__name__}"
    except Exception as e:
        return None, f"Unexpected error: {type(e).__name__}"
    finally:
        # Best-effort logout & wipe client state
        try:
            cl.logout()
        except Exception:
            pass
        try:
            cl.private.cookies.clear()
        except Exception:
            pass
        del cl


# ---------- 2FA Generator Flow ----------
async def totp_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "🔑 <b>2FA Generator</b>\n\n"
        "Send your <b>Base32 secret key</b> (e.g. <code>JBSWY3DPEHPK3PXP</code>):",
        parse_mode="HTML",
        reply_markup=back_kb(),
    )
    return TOTP_SECRET

async def totp_generate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text == BACK_BTN:
        return await cancel(update, context)

    secret = update.message.text.strip().replace(" ", "").upper()

    # Best-effort: delete the message containing the secret
    try:
        await update.message.delete()
    except Exception:
        pass

    try:
        totp = pyotp.TOTP(secret)
        code = totp.now()
        # Wipe local variable references
        del totp
    except Exception:
        secret = None
        await update.message.chat.send_message(
            "❌ <b>Invalid Base32 secret.</b> Please check and try again.",
            parse_mode="HTML",
            reply_markup=main_menu_kb(),
        )
        return ConversationHandler.END

    # Wipe secret from memory reference
    secret = None
    wipe(context)

    await update.message.chat.send_message(
        f"🔐 <b>Your current 2FA code:</b> <code>{code}</code>\n"
        "<i>(valid for up to 30 seconds)</i>",
        parse_mode="HTML",
        reply_markup=main_menu_kb(),
    )
    return ConversationHandler.END


# ---------- Cancel / Back ----------
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    wipe(context)
    await update.message.reply_text(
        "↩️ Cancelled. Back to main menu.",
        reply_markup=main_menu_kb(),
    )
    return ConversationHandler.END


# ---------- Error handler ----------
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Exception while handling an update: %s", context.error)
    try:
        if isinstance(update, Update) and update.effective_message:
            await update.effective_message.reply_text(
                "⚠️ Something went wrong. Please try again.",
                reply_markup=main_menu_kb(),
            )
    except Exception:
        pass


# ---------- Main ----------
def main() -> None:
    token = os.environ.get("BOT_TOKEN")
    if not token:
        raise RuntimeError("BOT_TOKEN environment variable is not set.")

    app = Application.builder().token(token).build()

    cookie_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(r"^🍪 Cookie's Extract$"), cookie_start)],
        states={
            COOKIE_USERNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, cookie_username)],
            COOKIE_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, cookie_password)],
            COOKIE_2FA: [MessageHandler(filters.TEXT & ~filters.COMMAND, cookie_2fa)],
        },
        fallbacks=[
            CommandHandler("start", start),
            MessageHandler(filters.Regex(f"^{BACK_BTN}$"), cancel),
        ],
        allow_reentry=True,
    )

    totp_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(r"^🔑 2FA Generator$"), totp_start)],
        states={
            TOTP_SECRET: [MessageHandler(filters.TEXT & ~filters.COMMAND, totp_generate)],
        },
        fallbacks=[
            CommandHandler("start", start),
            MessageHandler(filters.Regex(f"^{BACK_BTN}$"), cancel),
        ],
        allow_reentry=True,
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(cookie_conv)
    app.add_handler(totp_conv)
    app.add_handler(MessageHandler(filters.Regex(r"^👨‍💻 Developer$"), developer))
    app.add_handler(MessageHandler(filters.Regex(r"^📖 Guide$"), guide))
    app.add_handler(MessageHandler(filters.Regex(f"^{BACK_BTN}$"), cancel))

    app.add_error_handler(error_handler)

    logger.info("Bot starting...")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()
