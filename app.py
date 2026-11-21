import os
import time
import tempfile
import threading
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import yt_dlp

app = Flask(__name__)
CORS(app)

TEMP_DIR = tempfile.gettempdir()

def cleanup_old_files():
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

threading.Thread(target=cleanup_old_files, daemon=True).start()

@app.route('/')
def home():
    return "Retro Downloader API (240p Engine) is running."

@app.route('/download')
def download():
    url = request.args.get("url", "").strip()
    quality = request.args.get("quality", "240p")

    if not url:
        return jsonify(ok=False, error="Missing url"), 400

    if not url.startswith("http://") and not url.startswith("https://"):
        return jsonify(ok=False, error="Invalid URL scheme."), 400

    # Strict 240p. If it fails, fallback to 'worst' (144p), NEVER '/best'.
    # max_filesize is now strictly 25MB
    opts = {
        "format": "bestvideo[height<=240]+bestaudio/best[height<=240]/worst",
        "outtmpl": os.path.join(TEMP_DIR, "%(id)s.%(ext)s"),
        "merge_output_format": "mp4",
        "quiet": True,
        "noplaylist": True,
        "max_filesize": 25 * 1024 * 1024, # Strict 25MB limit
        "user_agent": "Mozilla/5.0 (Android 4.4; Mobile; rv:41.0) Gecko/41.0 Firefox/41.0"
    }

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            
            video_id = info.get("id")
            title = info.get("title", "Video")
            final_filename = f"{video_id}.mp4"
            
            host_url = request.host_url.rstrip('/')
            download_link = f"{host_url}/file/{final_filename}"

            return jsonify(
                ok=True,
                title=title,
                quality="240p",
                download_url=download_link
            )

    except Exception as exc:
        # If the file was too big, yt-dlp throws an error here
        error_msg = str(exc)
        if "File is larger than max-filesize" in error_msg:
             return jsonify(ok=False, error="Video is over 25MB. Try a shorter video."), 400
        return jsonify(ok=False, error=error_msg[:150]), 502

@app.route('/file/<filename>')
def serve_file(filename):
    # Force the download with headers Opera Mini understands
    response = send_from_directory(TEMP_DIR, filename, as_attachment=True, mimetype="video/mp4")
    response.headers["Content-Disposition"] = f"attachment; filename={filename}"
    return response

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
