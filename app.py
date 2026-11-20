from flask import Flask, request, jsonify, redirect
from flask_cors import CORS
import yt_dlp

app = Flask(__name__)
# Allow all domains to access this API (needed for GitHub Pages to connect)
CORS(app)

# Define quality formats
FORMATS = {
    "144p": "best[height<=144]/best",
    "240p": "best[height<=240]/best",
    "360p": "best[height<=360]/best",
}

@app.route('/')
def home():
    return "Retro Downloader API is running."

@app.route('/download')
def download():
    url = request.args.get("url", "").strip()
    quality = request.args.get("quality", "240p")
    wants_json = request.args.get("format") == "json"

    if not url:
        return jsonify(ok=False, error="Missing url"), 400

    # SSRF Protection: Ensure the URL is actually http or https
    if not url.startswith("http://") and not url.startswith("https://"):
        return jsonify(ok=False, error="Invalid URL scheme. Must be http or https."), 400

    opts = {
        "format": FORMATS.get(quality, FORMATS["240p"]),
        "quiet": True,
        "noplaylist": True,
        "skip_download": True,
        # Use a mobile user agent to help bypass some blocks
        "user_agent": "Mozilla/5.0 (Android 4.4; Mobile; rv:41.0) Gecko/41.0 Firefox/41.0"
    }

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            # Extract info without downloading
            info = ydl.extract_info(url, download=False)
            
            direct_url = info.get("url")
            if not direct_url:
                # Fallback: look through requested formats if direct url is missing
                formats = info.get("formats", [])
                if formats:
                    direct_url = formats[-1].get("url")

            if not direct_url:
                return jsonify(ok=False, error="No playable stream found for this video."), 502

            title = info.get("title", "Video")

            # Return JSON for the JavaScript frontend
            if wants_json:
                return jsonify(
                    ok=True,
                    title=title,
                    quality=quality,
                    download_url=direct_url
                )
            
            # Fallback for Opera Mini without JS: redirect directly to the file
            return redirect(direct_url, code=302)

    except Exception as exc:
        # Return error message if yt-dlp fails (e.g., age restriction, private video)
        return jsonify(ok=False, error=str(exc)[:150]), 502

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
