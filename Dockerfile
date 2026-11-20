FROM python:3.9-slim

# Install FFmpeg (crucial for merging 240p audio + video)
RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Increase timeout to 120s because downloading & merging takes time
CMD gunicorn app:app --bind 0.0.0.0:$PORT --timeout 120
