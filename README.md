# 🤖 Telegram Account Bot

A production-ready Telegram bot for account collection, fake identity generation,
admin notifications, and Excel-based data export.

---

## Features

| Button | What it does |
|---|---|
| ✅ Submit Account | Collects username, password, 2FA and saves to Excel |
| 🎭 Fake Info | Generates a random realistic identity |
| 👤 Admin | Notifies the admin on Telegram |
| 📥 Download | Sends `accounts.xlsx` to the user (and silently to admin) |

---

## Local Setup

### 1. Clone the repo

```bash
git clone [github.com](https://github.com/your-username/your-repo.git)
cd your-repo
```

### 2. Create a virtual environment

```bash
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Get a Bot Token

1. Open Telegram and search for **@BotFather**
2. Send `/newbot` and follow the prompts
3. Copy the token (looks like `123456789:ABCdef...`)

### 5. Get your Admin Chat ID

1. Start your bot once (send `/start`)
2. Visit: `[api.telegram.org](https://api.telegram.org/bot)<YOUR_TOKEN>/getUpdates`
3. Find your `"id"` in the JSON — that's your Chat ID

### 6. Set environment variables

```bash
export BOT_TOKEN="your_token_here"
export ADMIN_CHAT_ID="your_numeric_chat_id"
```

On Windows (PowerShell):

```powershell
$env:BOT_TOKEN="your_token_here"
$env:ADMIN_CHAT_ID="your_numeric_chat_id"
```

### 7. Run

```bash
python main.py
```

---

## Deploy on Railway

### Step 1 — Push to GitHub

Make sure your repo contains:
```
main.py
requirements.txt
Procfile
runtime.txt
README.md
```

> ⚠️ **Never commit your token.** Use environment variables only.

### Step 2 — Create Railway project

1. Go to [railway.app](https://railway.app) and sign in
2. Click **New Project → Deploy from GitHub repo**
3. Select your repository

### Step 3 — Set environment variables in Railway

In your Railway project dashboard:

- Go to **Variables** tab
- Add:
  - `BOT_TOKEN` = your bot token from BotFather
  - `ADMIN_CHAT_ID` = your numeric Telegram chat ID

### Step 4 — Deploy

Railway will automatically detect `Procfile` and start:
```
worker: python main.py
```

Monitor logs in the **Deployments** tab. You should see:
```
Bot starting — polling mode
```

---

## File Structure

```
.
├── main.py           # Bot logic (single file)
├── requirements.txt  # Python dependencies
├── Procfile          # Railway/Heroku process definition
├── runtime.txt       # Python version pin
├── README.md         # This file
└── accounts.xlsx     # Auto-created on first submission (gitignored)
```

Add `accounts.xlsx` to `.gitignore`:

```
accounts.xlsx
```

---

## Notes

- **ADMIN_CHAT_ID** must be a numeric ID, not a username. The admin must have
  started the bot at least once for notifications to work.
- The bot uses **long polling** — no webhook configuration needed.
- All data is stored locally in `accounts.xlsx`. On Railway, the file persists
  within a single deployment but resets on redeploy. For persistence, consider
  mounting a Railway volume or switching to a database.
- The 2FA field accepts any text or `-` / blank to skip.
- 
