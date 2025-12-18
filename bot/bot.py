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

# ---------------- CONFIG ---------------- #

BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_CHAT_ID"))

BACKEND_URL = os.environ.get(
    "BACKEND_URL",
    "https://tera-download-bot.onrender.com"
)

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

# ---------------- DB ---------------- #

def load_db():
    if DB_FILE.exists():
        return json.loads(DB_FILE.read_text())
    return {"authorized_users": {}}

def save_db(db):
    DB_FILE.write_text(json.dumps(db, indent=2))

def is_admin(uid):
    return uid == ADMIN_ID

def is_authorized(uid, db):
    return str(uid) in db["authorized_users"]

# ---------------- BACKEND ---------------- #

async def request_backend_download(url: str):
    timeout = aiohttp.ClientTimeout(total=1800)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(
            f"{BACKEND_URL}/download",
            json={"url": url}
        ) as resp:
            if resp.status != 200:
                raise Exception(await resp.text())
            return await resp.json()

async def fetch_file(filename: str):
    path = DOWNLOAD_DIR / filename
    timeout = aiohttp.ClientTimeout(total=1800)

    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(f"{BACKEND_URL}/file/{filename}") as resp:
            if resp.status != 200:
                raise Exception("Failed to fetch file")

            with open(path, "wb") as f:
                while True:
                    chunk = await resp.content.read(1024 * 1024)
                    if not chunk:
                        break
                    f.write(chunk)

    return path

# ---------------- WORKER ---------------- #

async def worker(app):
    try:
        while True:
            update, url = await download_queue.get()
            msg = await update.message.reply_text("⏳ Processing download…")

            try:
                result = await request_backend_download(url)
                filename = result["filename"]
                size_mb = result["size_mb"]

                await msg.edit_text(
                    f"📥 Downloaded ({size_mb} MB)\n📤 Uploading…"
                )

                file_path = await fetch_file(filename)

                with open(file_path, "rb") as f:
                    await update.message.reply_document(
                        document=f,
                        caption=f"✅ {filename}"
                    )

                file_path.unlink(missing_ok=True)
                await msg.delete()

            except Exception as e:
                await msg.edit_text(f"❌ Failed:\n{str(e)}")

            finally:
                download_queue.task_done()

    except asyncio.CancelledError:
        print("Worker cancelled safely")

# ---------------- COMMANDS ---------------- #

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    db = load_db()

    if uid == ADMIN_ID:
        await update.message.reply_text(
            "👋 Admin ready.\nSend any desktop TeraBox link."
        )
        return

    if is_authorized(uid, db):
        await update.message.reply_text("Send TeraBox link.")
        return

    await update.message.reply_text("⛔ Access denied.")

async def grant_access(update, context):
    if not is_admin(update.effective_user.id):
        return
    uid = context.args[0]
    db = load_db()
    db["authorized_users"][uid] = {}
    save_db(db)
    await update.message.reply_text("✅ Access granted")

# ---------------- HANDLER ---------------- #

async def handle_message(update, context):
    text = update.message.text or ""

    if not any(d in text for d in TERABOX_DOMAINS):
        return

    db = load_db()
    uid = update.effective_user.id

    if not (is_admin(uid) or is_authorized(uid, db)):
        return

    await download_queue.put((update, text))

# ---------------- MAIN ---------------- #

async def post_init(application):
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

    print("Bot started")
    app.run_polling()

if __name__ == "__main__":
    main()
