import os
import json
import asyncio
import re
from pathlib import Path
import subprocess
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

MAX_PARALLEL_DOWNLOADS = 3
PROGRESS_UPDATE_INTERVAL = 3

DATA_DIR = Path("./data")
DOWNLOAD_DIR = Path("./downloads")
DATA_DIR.mkdir(exist_ok=True)
DOWNLOAD_DIR.mkdir(exist_ok=True)

DB_FILE = DATA_DIR / "users.json"

download_queue = asyncio.Queue()

# ---------------- DB ---------------- #

def load_db():
    if DB_FILE.exists():
        return json.loads(DB_FILE.read_text())
    return {"authorized_users": {}}

def save_db(db):
    DB_FILE.write_text(json.dumps(db, indent=2))

# ---------------- HELPERS ---------------- #

def clean_filename(name: str):
    name = re.sub(r"[^\w\s-]", "", name)
    name = re.sub(r"\s+", "_", name)
    return name[:60]

def is_admin(uid):
    return uid == ADMIN_ID

def is_authorized(uid, db):
    return str(uid) in db["authorized_users"]

# ---------------- DOWNLOAD ---------------- #

async def download_terabox(url, progress_cb=None):
    output_tpl = DOWNLOAD_DIR / "%(title)s.%(ext)s"

    cmd = [
        "yt-dlp",
        "-f", "mp4/best",
        "--newline",
        "-o", str(output_tpl),
        url
    ]

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL
    )

    async for line in proc.stdout:
        if progress_cb:
            line = line.decode()
            if "%" in line:
                progress_cb(line.strip())

    await proc.wait()

    files = sorted(DOWNLOAD_DIR.glob("*"), key=os.path.getmtime, reverse=True)
    if not files:
        return None

    file = files[0]
    if file.suffix.lower() not in [".mp4", ".mkv", ".webm"]:
        return None

    cleaned = DOWNLOAD_DIR / f"{clean_filename(file.stem)}{file.suffix}"
    file.rename(cleaned)
    return cleaned

# ---------------- QUEUE WORKER ---------------- #

async def worker(app):
    while True:
        task = await download_queue.get()
        update, url, user_cfg = task

        msg = await update.message.reply_text("⏳ Downloading… 0%")

        def progress_cb(text):
            asyncio.create_task(
                msg.edit_text(f"⏳ Downloading… {text}")
            )

        file = await download_terabox(url, progress_cb)

        if not file:
            await msg.edit_text("❌ No downloadable video found")
            download_queue.task_done()
            continue

        await msg.edit_text("✅ Download complete")

        await update.message.reply_video(video=open(file, "rb"))

        if user_cfg and user_cfg.get("forwarder"):
            try:
                await app.bot.send_video(
                    chat_id=user_cfg["forwarder"],
                    video=open(file, "rb")
                )
            except:
                pass

        try:
            file.unlink()
        except:
            pass

        download_queue.task_done()

# ---------------- COMMANDS ---------------- #

async def grant_access(update, context):
    if not is_admin(update.effective_user.id):
        return

    uid = context.args[0]
    db = load_db()
    db["authorized_users"][uid] = {"channels": [], "forwarder": None}
    save_db(db)
    await update.message.reply_text("✅ Access granted")

async def set_channel(update, context):
    db = load_db()
    uid = str(update.effective_user.id)
    db["authorized_users"].setdefault(uid, {"channels": [], "forwarder": None})
    db["authorized_users"][uid]["channels"].append(context.args[0])
    save_db(db)
    await update.message.reply_text("✅ Channel added")

async def set_forwarder(update, context):
    db = load_db()
    uid = str(update.effective_user.id)
    db["authorized_users"].setdefault(uid, {"channels": [], "forwarder": None})
    db["authorized_users"][uid]["forwarder"] = int(context.args[0])
    save_db(db)
    await update.message.reply_text("✅ Forwarder set")

# ---------------- MESSAGE HANDLER ---------------- #

async def handle_message(update, context):
    text = update.message.text or ""
    if "terasharefile.com" not in text:
        return

    db = load_db()
    uid = str(update.effective_user.id)

    if not (is_admin(update.effective_user.id) or is_authorized(update.effective_user.id, db)):
        return

    await download_queue.put((update, text, db["authorized_users"].get(uid)))

# ---------------- MAIN ---------------- #

async def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("grantaccess", grant_access))
    app.add_handler(CommandHandler("setchannel", set_channel))
    app.add_handler(CommandHandler("setforwarder", set_forwarder))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    for _ in range(MAX_PARALLEL_DOWNLOADS):
        asyncio.create_task(worker(app))

    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
