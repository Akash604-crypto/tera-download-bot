import os
import subprocess
from pathlib import Path
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from fastapi.responses import FileResponse

app = FastAPI()

BASE = Path(".")
DOWNLOADS = BASE / "downloads"
COOKIES = BASE / "cookies"

DOWNLOADS.mkdir(exist_ok=True)

class DownloadReq(BaseModel):
    url: str

def normalize(url: str) -> str:
    url = url.strip()
    url = url.replace("www.", "")
    url = url.replace("teraboxurl.com", "1024terabox.com")
    url = url.replace("terabox.app", "1024terabox.com")
    return url

def is_blocked(url: str) -> bool:
    return "/wap/" in url or "filelist" in url

def cookie_for(url: str) -> Path | None:
    if "1024terabox.com" in url:
        return COOKIES / "cookies_1024.txt"
    if "terasharefile.com" in url:
        return COOKIES / "cookies_terasharefile.txt"
    return None

@app.post("/download")
def download(req: DownloadReq):
    url = normalize(req.url)

    if is_blocked(url):
        raise HTTPException(400, "Mobile/WAP links are not supported")

    cookie = cookie_for(url)
    if not cookie or not cookie.exists():
        raise HTTPException(400, "No cookie for this link")

    out = DOWNLOADS / "%(title)s.%(ext)s"

    cmd = [
        "yt-dlp",
        "--cookies", str(cookie),
        "--user-agent", "Mozilla/5.0",
        "--socket-timeout", "120",
        "--retries", "3",
        "--fragment-retries", "2",
        "--merge-output-format", "mp4",
        "-o", str(out),
        url
    ]

    run = subprocess.run(cmd, capture_output=True, text=True)

    if run.returncode != 0:
        raise HTTPException(500, "Download failed")

    files = sorted(DOWNLOADS.glob("*"), key=os.path.getmtime, reverse=True)
    if not files:
        raise HTTPException(404, "No file created")

    f = files[0]
    size_mb = round(f.stat().st_size / (1024 * 1024), 2)

    return {"filename": f.name, "size_mb": size_mb}

@app.get("/file/{name}")
def file(name: str):
    p = DOWNLOADS / name
    if not p.exists():
        raise HTTPException(404)
    return FileResponse(p, filename=name)
