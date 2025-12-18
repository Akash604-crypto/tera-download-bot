import os
import subprocess
from pathlib import Path
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from fastapi.responses import FileResponse

app = FastAPI()

BASE_DIR = Path(".")
DOWNLOAD_DIR = BASE_DIR / "downloads"
COOKIE_DIR = BASE_DIR / "cookies"

DOWNLOAD_DIR.mkdir(exist_ok=True)

class DownloadReq(BaseModel):
    url: str


def get_cookie_for_url(url: str):
    if "1024terabox.com" in url:
        return COOKIE_DIR / "cookies_1024.txt"
    if "teraboxurl.com" in url:
        return COOKIE_DIR / "cookies_teraboxurl.txt"
    if "terasharefile.com" in url:
        return COOKIE_DIR / "cookies_terasharefile.txt"
    return None


@app.post("/download")
def download(req: DownloadReq):
    cookie = get_cookie_for_url(req.url)
    if not cookie or not cookie.exists():
        raise HTTPException(400, "No valid cookie for this link")

    output = DOWNLOAD_DIR / "%(title)s.%(ext)s"

    cmd = [
        "yt-dlp",
        "--cookies", str(cookie),
        "--user-agent", "Mozilla/5.0 (Linux; Android 12)",
        "--referer", "https://www.terabox.com/",
        "--no-check-certificate",
        "--retries", "10",
        "--fragment-retries", "10",
        "--extractor-retries", "10",
        "--socket-timeout", "30",
        "-f", "bv*+ba/b/best",
        "--merge-output-format", "mp4",
        "-o", str(output),
        req.url
    ]

    run = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    if run.returncode != 0:
        print("yt-dlp STDOUT:\n", run.stdout)
        print("yt-dlp STDERR:\n", run.stderr)
        raise HTTPException(500, "yt-dlp failed")

    files = [
        f for f in DOWNLOAD_DIR.iterdir()
        if f.is_file() and not f.name.endswith((".part", ".ytdlp"))
    ]

    if not files:
        raise HTTPException(404, "No file created")

    file = max(files, key=lambda f: f.stat().st_mtime)
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
