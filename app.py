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
            if f.endswith('.mp4') or f.endswith('.webm') or f.endswith('.3gp') or f.endswith('.m4a'):
                filepath = os.path.join(TEMP_DIR, f)
                if os.path.getmtime(filepath) < now - 600:
                    try:
                        os.remove(filepath)
                    except:
                        pass

threading.Thread(target=cleanup_old_files, daemon=True).start()

@app.route('/')
def home():
    return "Retro Downloader API is running."

@app.route('/download')
def download():
    url = request.args.get("url", "").strip()

    if not url or not url.startswith("http"):
        return jsonify(ok=False, error="Invalid URL."), 400

    opts = {
        # Strict 240p. If not available, it fails. NO '/worst' fallback.
        "format": "bestvideo[height<=240]+bestaudio/best[height<=240]",
        "outtmpl": os.path.join(TEMP_DIR, "%(id)s.%(ext)s"),
        "merge_output_format": "mp4",
        "quiet": True,
        "noplaylist": True,
        "max_filesize": 50 * 1024 * 1024, # Strict 50MB limit
        "user_agent": "Mozilla/5.0 (Android 4.4; Mobile; rv:41.0) Gecko/41.0 Firefox/41.0"
    }

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            
            filepath = None
            if 'requested_downloads' in info and info['requested_downloads']:
                filepath = info['requested_downloads'][0].get('filepath')
            
            if not filepath or not os.path.exists(filepath):
                return jsonify(ok=False, error="Video exceeds 50MB or failed to download."), 400

            actual_filename = os.path.basename(filepath)
            title = info.get("title", "Video")
            
            host_url = request.host_url.rstrip('/')
            download_link = f"{host_url}/file/{actual_filename}"

            return jsonify(
                ok=True,
                title=title,
                quality="240p",
                download_url=download_link
            )

    except Exception as exc:
        error_msg = str(exc)
        
        # Handle the 50MB size limit
        if "File is larger than max-filesize" in error_msg:
             return jsonify(ok=False, error="This site's lowest quality is over 50MB. Try a shorter video."), 400
             
        # Handle when a site doesn't have 240p at all
        if "Requested format is not available" in error_msg:
             return jsonify(ok=False, error="This site does not offer a 240p version."), 400
             
        return jsonify(ok=False, error=error_msg[:150]), 502

@app.route('/file/<filename>')
def serve_file(filename):
    response = send_from_directory(TEMP_DIR, filename, as_attachment=True, mimetype="application/octet-stream")
    response.headers["Content-Disposition"] = f"attachment; filename={filename}"
    return response

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
