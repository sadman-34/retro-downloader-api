import os
import time
import tempfile
import threading
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import yt_dlp

app = Flask(__name__)
CORS(app)

# Use Render's temporary directory
TEMP_DIR = tempfile.gettempdir()

def cleanup_old_files():
    """Deletes files older than 10 minutes to save space on Render."""
    while True:
        time.sleep(600)
        now = time.time()
        for f in os.listdir(TEMP_DIR):
            if f.endswith('.mp4'):
                filepath = os.path.join(TEMP_DIR, f)
                if os.path.getmtime(filepath) < now - 600:
                    try:
                        os.remove(filepath)
                    except:
                        pass

# Start cleanup thread in background
threading.Thread(target=cleanup_old_files, daemon=True).start()

@app.route('/')
def home():
    return "Retro Downloader API (240p Merge Engine) is running."

@app.route('/download')
def download():
    url = request.args.get("url", "").strip()
    quality = request.args.get("quality", "240p")

    if not url:
        return jsonify(ok=False, error="Missing url"), 400

    if not url.startswith("http://") and not url.startswith("https://"):
        return jsonify(ok=False, error="Invalid URL scheme."), 400

    # Force yt-dlp to grab 240p video + best audio and merge them as mp4
    opts = {
        "format": "bestvideo[height<=240]+bestaudio[ext=m4a]/best[height<=240]/best",
        "outtmpl": os.path.join(TEMP_DIR, "%(id)s.%(ext)s"),
        "merge_output_format": "mp4",
        "quiet": True,
        "noplaylist": True,
        "user_agent": "Mozilla/5.0 (Android 4.4; Mobile; rv:41.0) Gecko/41.0 Firefox/41.0"
    }

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            # THIS ACTUALLY DOWNLOADS AND MERGES THE FILE
            info = ydl.extract_info(url, download=True)
            
            video_id = info.get("id")
            title = info.get("title", "Video")
            final_filename = f"{video_id}.mp4"
            
            # Get the public URL of your Render backend
            host_url = request.host_url.rstrip('/')
            download_link = f"{host_url}/file/{final_filename}"

            return jsonify(
                ok=True,
                title=title,
                quality="240p",
                download_url=download_link
            )

    except Exception as exc:
        return jsonify(ok=False, error=str(exc)[:150]), 502

@app.route('/file/<filename>')
def serve_file(filename):
    """Serves the merged MP4 file to the phone."""
    return send_from_directory(TEMP_DIR, filename, as_attachment=True)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
