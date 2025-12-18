FROM python:3.11-slim

# Prevent Python buffering issues
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Copy files
COPY . .

# Install system deps (needed by yt-dlp)
RUN apt-get update && apt-get install -y ffmpeg curl \
    && rm -rf /var/lib/apt/lists/*

# Install python deps
RUN pip install --no-cache-dir -r requirements.txt

# Start bot
CMD ["python", "bot.py"]
