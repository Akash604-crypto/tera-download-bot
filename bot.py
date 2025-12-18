import os
import json
import asyncio
import aiohttp
from pathlib import Path
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ================= CONFIG ================= #

BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_CHAT_ID"))

BACKEND_URL = os.environ.get(
    "BACKEND_URL",
    "https://terabox-backend.onrender.com"  # CHANGE IF NEEDED
)

MAX_WORKERS = 3

DATA_DIR = Path("./data")
DOWNLOAD_DIR = Path("./downloads")

DATA_DIR.mkdir(exist_ok=True)
DOWNLOAD_DIR.mkdir(exist_ok=True)

DB_FILE = DATA_DIR / "users.json"
download_queue = asyncio.Queue()

TERABOX_DOMAINS = (
    "terabox",
    "1024terabox",
    "terasharefile",
)

# ================= DB ================= #

def load_db():
    if DB_FILE.exists():
        return json.loads(DB_FILE.read_text())
    return {"authorized_users": {}}

def save_db(db):
    DB_FILE.write_text(json.dumps(db, indent=2))

def is_admin(uid: int) -> bool:
    return uid == ADMIN_ID

def is_authorized(uid: int, db: dict) -> bool:
    return str(uid) in db["authorized_users"]

# ================= BACKEND CALLS ================= #

async def request_backend_download(url: str):
    async with aiohttp.ClientSession(
        timeout=aiohttp.ClientTimeout(total=1800)
    ) as session:
        try:
            async with session.post(
                f"{BACKEND_URL}/download",
                json={"url": url}
            ) as resp:
                if resp.status != 200:
                    raise Exception(await resp.text())
                return await resp.json()
        except aiohttp.ClientConnectorError:
            raise Exception("Backend is offline or sleeping")

async def fetch_file_from_backend(filename: str):
    file_path = DOWNLOAD_DIR / filename

    async with aiohttp.ClientSession(
        timeout=aiohttp.ClientTimeout(total=1800)
    ) as session:
        async with session.get(f"{BACKEND_URL}/file/{filename}") as resp:
            if resp.status != 200:
                raise Exception("Failed to fetch file from backend")

            with open(file_path, "wb") as f:
                while True:
                    chunk = await resp.content.read(1024 * 1024)
                    if not chunk:
                        break
                    f.write(chunk)

    return file_path

# ================= WORKER ================= #

async def worker(app):
    while True:
        update, url = await download_queue.get()
        msg = await update.message.reply_text("⏳ Processing download...")

        try:
            result = await request_backend_download(url)

            filename = result["filename"]
            size_mb = result["size_mb"]

            await msg.edit_text(
                f"📥 Downloaded on server ({size_mb} MB)\n📤 Uploading to Telegram..."
            )

            file_path = await fetch_file_from_backend(filename)

            with open(file_path, "rb") as f:
                if filename.lower().endswith((".mp4", ".mkv", ".mov")):
                    await update.message.reply_video(
                        video=f,
                        caption=f"✅ {filename}",
                        supports_streaming=True
                    )
                else:
                    await update.message.reply_document(
                        document=f,
                        caption=f"✅ {filename}"
                    )

            file_path.unlink(missing_ok=True)
            await msg.delete()

        except Exception as e:
            await msg.edit_text(f"❌ Failed:\n{str(e)}")

        download_queue.task_done()

# ================= COMMANDS ================= #

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    db = load_db()

    if is_admin(uid):
        await update.message.reply_text(
            "👋 Admin Ready\n\n"
            "Send any TeraBox link to download."
        )
        return

    if is_authorized(uid, db):
        await update.message.reply_text(
            "👋 Send a TeraBox link to start download."
        )
        return

    await update.message.reply_text("⛔ Access denied. Contact admin.")

async def grant_access(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    if not context.args:
        await update.message.reply_text("Usage: /grantaccess <user_id>")
        return

    uid = context.args[0]
    db = load_db()
    db["authorized_users"][uid] = {}
    save_db(db)

    await update.message.reply_text("✅ Access granted")

# ================= MESSAGE HANDLER ================= #

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text or ""

    if not any(d in text for d in TERABOX_DOMAINS):
        return

    db = load_db()
    uid = update.effective_user.id

    if not (is_admin(uid) or is_authorized(uid, db)):
        return

    await download_queue.put((update, text))

# ================= MAIN ================= #

async def post_init(application):
    for _ in range(MAX_WORKERS):
        application.create_task(worker(application))

def main():
    app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("grantaccess", grant_access))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("🤖 Bot started")
    app.run_polling()

if __name__ == "__main__":
    main()
