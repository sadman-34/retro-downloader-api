from flask import Flask, request, jsonify
from flask_cors import CORS
import yt_dlp

app = Flask(__name__)
CORS(app)  # Lets your GitHub Pages site talk to this API

@app.route("/api/extract")
def extract():
    url = request.args.get("url", "").strip()
    quality = request.args.get("quality", "240p")

    if not url:
        return jsonify({"error": "No URL provided"}), 400

    # Pick a single pre-merged format up to the requested height (best for feature phones)
    height_map = {"144p": 144, "240p": 240, "360p": 360}
    if quality == "audio":
        fmt = "bestaudio[ext=m4a]/bestaudio"
    else:
        max_h = height_map.get(quality, 240)
        fmt = f"best[height<={max_h}][ext=mp4]/best[height<={max_h}]/best"

    ydl_opts = {
        "format": fmt,
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            direct_url = info.get("url")
            if not direct_url:
                return jsonify({"error": "Could not find a direct stream URL."}), 404

            size_bytes = info.get("filesize") or info.get("filesize_approx")
            size_str = f"{round(size_bytes / (1024 * 1024), 1)} MB" if size_bytes else ""

            return jsonify({
                "title": info.get("title", "Video"),
                "quality": quality,
                "size": size_str,
                "download_url": direct_url
            })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)