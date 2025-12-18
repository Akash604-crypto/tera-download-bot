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

# Load cookies
COOKIES = list(COOKIE_DIR.glob("*.txt"))
COOKIE_COOLDOWN = {}

COOLDOWN_SECONDS = 90

class DownloadReq(BaseModel):
    url: str

def pick_cookie():
    now = time.time()
    random.shuffle(COOKIES)

    for c in COOKIES:
        last = COOKIE_COOLDOWN.get(c.name, 0)
        if now - last >= COOLDOWN_SECONDS:
            COOKIE_COOLDOWN[c.name] = now
            return c
    return None

@app.post("/download")
def download(req: DownloadReq):
    cookie = pick_cookie()
    if not cookie:
        raise HTTPException(status_code=429, detail="All cookies cooling down")

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

    proc = subprocess.run(cmd, capture_output=True)

    if proc.returncode != 0:
        raise HTTPException(status_code=500, detail="yt-dlp failed")

    files = sorted(DOWNLOAD_DIR.glob("*"), key=os.path.getmtime, reverse=True)
    if not files:
        raise HTTPException(status_code=404, detail="No file created")

    file = files[0]
    size_mb = round(file.stat().st_size / (1024 * 1024), 2)

    return {
        "filename": file.name,
        "size_mb": size_mb
    }
