import os
import time
import random
import subprocess
from pathlib import Path
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI()

BASE_DIR = Path(".")
DOWNLOAD_DIR = BASE_DIR / "downloads"
COOKIE_DIR = BASE_DIR / "cookies"

DOWNLOAD_DIR.mkdir(exist_ok=True)

COOKIES = list(COOKIE_DIR.glob("*.txt"))
COOKIE_LAST_USED = {}
COOLDOWN = 90  # seconds

class DownloadReq(BaseModel):
    url: str

def get_cookie():
    now = time.time()
    random.shuffle(COOKIES)

    for c in COOKIES:
        last = COOKIE_LAST_USED.get(c.name, 0)
        if now - last > COOLDOWN:
            COOKIE_LAST_USED[c.name] = now
            return c
    return None

@app.post("/download")
def download(req: DownloadReq):
    cookie = get_cookie()
    if not cookie:
        raise HTTPException(429, "All cookies are cooling down")

    output = DOWNLOAD_DIR / "%(title)s.%(ext)s"

    cmd = [
        "yt-dlp",
        "--cookies", str(cookie),
        "--user-agent", "Mozilla/5.0",
        "--merge-output-format", "mp4",
        "--retries", "5",
        "--fragment-retries", "5",
        "-o", str(output),
        req.url
    ]

    run = subprocess.run(cmd, capture_output=True)

    if run.returncode != 0:
        raise HTTPException(500, "Download failed")

    files = sorted(DOWNLOAD_DIR.glob("*"), key=os.path.getmtime, reverse=True)
    if not files:
        raise HTTPException(404, "No file created")

    file = files[0]
    size_mb = round(file.stat().st_size / (1024 * 1024), 2)

    return {
        "filename": file.name,
        "size_mb": size_mb
    }
