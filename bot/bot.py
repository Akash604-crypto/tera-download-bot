import os, json, asyncio, aiohttp
from pathlib import Path
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, ContextTypes, filters

BOT_TOKEN = os.environ["BOT_TOKEN"]
ADMIN_ID = int(os.environ["ADMIN_CHAT_ID"])
BACKEND = os.environ["BACKEND_URL"]

DATA = Path("data")
DL = Path("downloads")
DATA.mkdir(exist_ok=True)
DL.mkdir(exist_ok=True)

DB = DATA / "users.json"
queue = asyncio.Queue()

def load_db():
    if DB.exists():
        return json.loads(DB.read_text())
    return {"authorized_users": {}}

def is_allowed(uid, db):
    return uid == ADMIN_ID or str(uid) in db["authorized_users"]

async def backend_download(url):
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=1800)) as s:
        async with s.post(f"{BACKEND}/download", json={"url": url}) as r:
            if r.status != 200:
                raise Exception(await r.text())
            return await r.json()

async def backend_fetch(name):
    path = DL / name
    async with aiohttp.ClientSession() as s:
        async with s.get(f"{BACKEND}/file/{name}") as r:
            if r.status != 200:
                raise Exception("Fetch failed")
            with open(path, "wb") as f:
                async for c in r.content.iter_chunked(1024*1024):
                    f.write(c)
    return path

async def worker(app):
    while True:
        upd, url = await queue.get()
        msg = await upd.message.reply_text("⏳ Processing…")
        try:
            res = await backend_download(url)
            file = await backend_fetch(res["filename"])
            with open(file, "rb") as f:
                await upd.message.reply_document(f, caption=f"✅ {res['filename']}")
            file.unlink(missing_ok=True)
            await msg.delete()
        except Exception as e:
            await msg.edit_text(f"❌ {e}")
        queue.task_done()

async def start(update: Update, _: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Send TeraBox link")

async def handle(update: Update, _: ContextTypes.DEFAULT_TYPE):
    db = load_db()
    if not is_allowed(update.effective_user.id, db):
        return
    await queue.put((update, update.message.text.strip()))

async def post_init(app):
    app.create_task(worker(app))

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))
    app.run_polling()

if __name__ == "__main__":
    main()
