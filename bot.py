import os
import json
import asyncio
import re
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

MAX_PARALLEL_DOWNLOADS = 3

DATA_DIR = Path("./data")
DOWNLOAD_DIR = Path("./downloads")
DATA_DIR.mkdir(exist_ok=True)
DOWNLOAD_DIR.mkdir(exist_ok=True)

DB_FILE = DATA_DIR / "users.json"
download_queue = asyncio.Queue()

# ================= DB ================= #

def load_db():
    if DB_FILE.exists():
        return json.loads(DB_FILE.read_text())
    return {"authorized_users": {}}

def save_db(db):
    DB_FILE.write_text(json.dumps(db, indent=2))

# ================= HELPERS ================= #

def clean_filename(name: str):
    name = re.sub(r"[^\w\s-]", "", name)
    name = re.sub(r"\s+", "_", name)
    return name[:60]

def is_admin(uid):
    return uid == ADMIN_ID

def is_authorized(uid, db):
    return str(uid) in db["authorized_users"]

def get_cookie_file(url: str):
    if "1024terabox.com" in url:
        return "cookies/cookies_1024.txt"
    if "teraboxurl.com" in url:
        return "cookies/cookies_teraboxurl.txt"
    if "terasharefile.com" in url:
        return "cookies/cookies_terasharefile.txt"
    return None

# ================= DOWNLOAD ================= #

async def download_terabox(url, progress_cb=None):
    cookie_file = get_cookie_file(url)
    if not cookie_file or not os.path.exists(cookie_file):
        return None

    output_tpl = DOWNLOAD_DIR / "%(title)s.%(ext)s"

    cmd = [
        "yt-dlp",
        "--cookies", cookie_file,
        "--user-agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "--referer", "https://www.terabox.com/",
        "--no-check-certificate",
        "--ignore-errors",
        "--no-warnings",
        "--retries", "5",
        "-f", "bestvideo+bestaudio/best",
        "--merge-output-format", "mp4",
        "-o", str(output_tpl),
        url
    ]

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )

    async for line in proc.stdout:
        if progress_cb and b"%" in line:
            progress_cb(line.decode(errors="ignore").strip())

    await proc.wait()

    files = sorted(DOWNLOAD_DIR.glob("*.mp4"), key=os.path.getmtime, reverse=True)
    if not files:
        return None

    file = files[0]
    cleaned = DOWNLOAD_DIR / f"{clean_filename(file.stem)}{file.suffix}"
    if file != cleaned:
        file.rename(cleaned)

    return cleaned

# ================= WORKER ================= #

async def worker(app):
    while True:
        update, url, user_cfg = await download_queue.get()

        msg = await update.message.reply_text("⏳ Downloading…")

        def progress_cb(text):
            app.create_task(msg.edit_text(f"⏳ {text}"))

        try:
            file = await download_terabox(url, progress_cb)
        except Exception:
            file = None

        if not file:
            await msg.edit_text("❌ No downloadable video found")
            download_queue.task_done()
            continue

        await msg.edit_text("✅ Download complete")

        with open(file, "rb") as f:
            await update.message.reply_video(video=f)

        if user_cfg and user_cfg.get("forwarder"):
            try:
                with open(file, "rb") as f:
                    await app.bot.send_video(
                        chat_id=user_cfg["forwarder"],
                        video=f
                    )
            except:
                pass

        try:
            file.unlink()
        except:
            pass

        download_queue.task_done()

# ================= COMMANDS ================= #

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    db = load_db()

    if uid == ADMIN_ID:
        await update.message.reply_text(
            "👋 Welcome, Admin!\n\n"
            "Commands:\n"
            "• /grantaccess <user_id>\n"
            "• /setchannel <invite_link>\n"
            "• /setforwarder <channel_id>\n\n"
            "Send any Terabox link to download."
        )
        return

    if str(uid) in db["authorized_users"]:
        await update.message.reply_text(
            "👋 Welcome!\n\n"
            "Setup:\n"
            "1️⃣ /setchannel <invite_link>\n"
            "2️⃣ /setforwarder <channel_id>\n\n"
            "Then send Terabox links."
        )
        return

    await update.message.reply_text(
        "⛔ Access denied.\nContact admin."
    )

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

# ================= MESSAGE HANDLER ================= #

TERABOX_DOMAINS = (
    "terabox.com",
    "teraboxapp.com",
    "teraboxurl.com",
    "terasharefile.com",
    "1024terabox.com",
)

async def handle_message(update, context):
    text = update.message.text or ""
    if not any(domain in text for domain in TERABOX_DOMAINS):
        return

    db = load_db()
    uid = update.effective_user.id

    if not (is_admin(uid) or is_authorized(uid, db)):
        return

    await download_queue.put(
        (update, text, db["authorized_users"].get(str(uid)))
    )

# ================= MAIN ================= #

async def post_init(application):
    for _ in range(MAX_PARALLEL_DOWNLOADS):
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
    app.add_handler(CommandHandler("setchannel", set_channel))
    app.add_handler(CommandHandler("setforwarder", set_forwarder))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Bot started")
    app.run_polling()

if __name__ == "__main__":
    main()
