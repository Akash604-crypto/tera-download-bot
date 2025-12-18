from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import subprocess, os, time, random
from pathlib import Path

app = FastAPI()

DOWNLOAD_DIR = Path("downloads")
COOKIE_DIR = Path("cookies")

DOWNLOAD_DIR.mkdir(exist_ok=True)

COOKIE_POOL = list(COOKIE_DIR.glob("*.txt"))
COOKIE_COOLDOWN = {}

class DownloadRequest(BaseModel):
    url: str

def get_cookie():
    now = time.time()
    random.shuffle(COOKIE_POOL)

    for cookie in COOKIE_POOL:
        last = COOKIE_COOLDOWN.get(cookie.name, 0)
        if now - last > 90:  # 90 sec cooldown
            COOKIE_COOLDOWN[cookie.name] = now
            return cookie
    return None

@app.post("/download")
def download(req: DownloadRequest):
    cookie = get_cookie()
    if not cookie:
        raise HTTPException(429, "All cookies cooling down")

    output = DOWNLOAD_DIR / "%(title)s.%(ext)s"

    cmd = [
        "yt-dlp",
        "--cookies", str(cookie),
        "--user-agent", "Mozilla/5.0",
        "--merge-output-format", "mp4",
        "-o", str(output),
        req.url
    ]

    proc = subprocess.run(cmd, capture_output=True)

    if proc.returncode != 0:
        raise HTTPException(500, "Download failed")

    files = sorted(DOWNLOAD_DIR.glob("*"), key=os.path.getmtime, reverse=True)
    if not files:
        raise HTTPException(404, "No file produced")

    file = files[0]
    size_mb = file.stat().st_size / (1024 * 1024)

    return {
        "file": file.name,
        "size_mb": round(size_mb, 2)
    }
