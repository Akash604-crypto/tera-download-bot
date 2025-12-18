import os
import subprocess
import time
from pathlib import Path
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from fastapi.responses import FileResponse

app = FastAPI()

BASE_DIR = Path(".")
DOWNLOAD_DIR = BASE_DIR / "downloads"
COOKIE_DIR = BASE_DIR / "cookies"

DOWNLOAD_DIR.mkdir(exist_ok=True)
COOKIE_DIR.mkdir(exist_ok=True)

class DownloadReq(BaseModel):
    url: str

# ---------------- HELPERS ---------------- #

def is_blocked(url: str) -> bool:
    return (
        "/wap/" in url
        or "filelist" in url
        or "surl=" in url
    )

def get_cookie_for_url(url: str) -> Path | None:
    if "1024terabox.com" in url:
        return COOKIE_DIR / "cookies_1024.txt"
    if "teraboxurl.com" in url:
        return COOKIE_DIR / "cookies_teraboxurl.txt"
    if "terasharefile.com" in url:
        return COOKIE_DIR / "cookies_terasharefile.txt"
    if "terabox.com" in url:
        return COOKIE_DIR / "cookies_1024.txt"
    return None

# ---------------- API ---------------- #

@app.post("/download")
def download(req: DownloadReq):
    url = req.url.strip()

    if is_blocked(url):
        raise HTTPException(
            400,
            "Mobile/WAP TeraBox link detected. Open link in desktop mode and resend."
        )

    cookie = get_cookie_for_url(url)
    if not cookie or not cookie.exists():
        raise HTTPException(400, "No valid cookie for this link")

    output_tpl = DOWNLOAD_DIR / "%(title)s.%(ext)s"

    cmd = [
        "yt-dlp",
        "--cookies", str(cookie),
        "--user-agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "--referer", "https://www.terabox.com/",
        "--no-check-certificate",
        "--ignore-errors",
        "--retries", "5",
        "--fragment-retries", "5",
        "--socket-timeout", "30",
        "-f", "bestvideo+bestaudio/best",
        "--merge-output-format", "mp4",
        "-o", str(output_tpl),
        url,
    ]

    run = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    if run.returncode != 0:
        print("STDOUT:\n", run.stdout)
        print("STDERR:\n", run.stderr)
        raise HTTPException(500, "yt-dlp failed")

    files = sorted(DOWNLOAD_DIR.glob("*"), key=os.path.getmtime, reverse=True)
    if not files:
        raise HTTPException(404, "No file created")

    file = files[0]
    size_mb = round(file.stat().st_size / (1024 * 1024), 2)

    return {
        "filename": file.name,
        "size_mb": size_mb
    }

@app.get("/file/{filename}")
def get_file(filename: str):
    file_path = DOWNLOAD_DIR / filename
    if not file_path.exists():
        raise HTTPException(404, "File not found")
    return FileResponse(file_path, filename=filename)
