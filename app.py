from flask import Flask, request, jsonify
from flask_cors import CORS
import urllib.parse
import urllib.request
import re
import html
import yt_dlp

app = Flask(__name__)
CORS(app)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def normalize_input_url(url):
    """Normalize mobile/shortcut URLs so yt-dlp extractors match cleanly."""
    u = url.strip()
    if not re.match(r"^https?://", u, re.IGNORECASE):
        u = "https://" + u

    # Convert xnxx.com/mobile/... to www.xnxx.com/...
    u = re.sub(
        r"^https?://(www\.|m\.)?xnxx\.com/mobile/",
        "https://www.xnxx.com/",
        u,
        flags=re.IGNORECASE,
    )
    u = re.sub(
        r"^https?://m\.xnxx\.com/",
        "https://www.xnxx.com/",
        u,
        flags=re.IGNORECASE,
    )
    return u


def format_duration(val):
    if not val:
        return ""
    if isinstance(val, str):
        return val
    if isinstance(val, (int, float)):
        secs = int(val)
        if secs >= 3600:
            return f"{secs // 3600}:{(secs % 3600) // 60:02d}:{secs % 60:02d}"
        return f"{secs // 60}:{secs % 60:02d}"
    return ""


def is_direct_progressive(fmt):
    """Accept direct HTTP MP4/3GP streams even if vcodec/acodec metadata is omitted."""
    url = fmt.get("url") or ""
    if not url.startswith("http"):
        return False

    lower_url = url.lower()
    if ".m3u8" in lower_url or ".mpd" in lower_url or ".ts" in lower_url:
        return False

    proto = (fmt.get("protocol") or "").lower()
    if "m3u8" in proto or "dash" in proto:
        return False

    # Exclude known audio-only tracks
    vcodec = (fmt.get("vcodec") or "").lower()
    fmt_id = (fmt.get("format_id") or "").lower()
    ext = (fmt.get("ext") or "").lower()
    if vcodec == "none" or ext in ("m4a", "mp3", "ogg", "opus", "aac"):
        return False
    if "audio" in fmt_id and "video" not in fmt_id:
        return False

    return True


def pick_best_direct_format(info, quality):
    """Choose a direct non-m3u8 video (or audio) format matching quality."""
    formats = info.get("formats") or []

    if quality == "audio":
        audio_cands = []
        for f in formats:
            url = f.get("url") or ""
            proto = (f.get("protocol") or "").lower()
            if (
                url.startswith("http")
                and ".m3u8" not in url.lower()
                and "m3u8" not in proto
                and "dash" not in proto
                and ((f.get("vcodec") or "").lower() == "none" or (f.get("ext") or "").lower() in ("m4a", "mp3"))
            ):
                audio_cands.append(f)
        if audio_cands:
            audio_cands.sort(key=lambda x: (
                1 if (x.get("ext") in ("m4a", "mp3")) else 0,
                x.get("abr") or 0,
                x.get("tbr") or 0,
            ))
            best_a = audio_cands[-1]
            return best_a.get("url"), best_a.get("filesize") or best_a.get("filesize_approx")

    height_map = {"144p": 144, "240p": 240, "360p": 360}
    target_h = height_map.get(quality, 240)

    candidates = [f for f in formats if is_direct_progressive(f)]

    if candidates:
        def score_fmt(f):
            h = f.get("height") or 0
            ext = (f.get("ext") or "").lower()
            fmt_id = (f.get("format_id") or "").lower()

            # Handle sites like XNXX that label formats 'mp4-low' / 'mp4-high' without height numbers
            if h == 0 and "low" in fmt_id:
                h = 240
            elif h == 0 and "high" in fmt_id:
                h = 480

            within_cap = 1 if (0 < h <= target_h) else (0 if h == 0 else -1)
            ext_rank = 2 if ext == "mp4" else (1 if ext == "3gp" else 0)
            return (within_cap, ext_rank, h if h <= target_h else -h, f.get("tbr") or 0)

        candidates.sort(key=score_fmt)
        best = candidates[-1]
        return best.get("url"), best.get("filesize") or best.get("filesize_approx")

    top_url = info.get("url") or ""
    if top_url and ".m3u8" not in top_url.lower():
        return top_url, info.get("filesize") or info.get("filesize_approx")

    return None, None


@app.route("/")
def home():
    return jsonify({"status": "ok", "service": "retro-downloader-api"})


@app.route("/api/extract")
def extract():
    raw_url = request.args.get("url", "").strip()
    quality = request.args.get("quality", "240p")

    if not raw_url:
        return jsonify({"error": "No URL provided"}), 400

    url = normalize_input_url(raw_url)

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "socket_timeout": 15,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info:
                return jsonify({"error": "Could not read video info."}), 400

            direct_url, size_bytes = pick_best_direct_format(info, quality)
            if not direct_url:
                return jsonify({
                    "error": "No direct MP4/3GP file found (only HLS .m3u8 stream available)."
                }), 404

            size_bytes = size_bytes or info.get("filesize") or info.get("filesize_approx")
            size_str = f"{round(size_bytes / (1024 * 1024), 1)} MB" if size_bytes else ""

            return jsonify({
                "title": info.get("title", "Video"),
                "quality": quality,
                "size": size_str,
                "download_url": direct_url,
            })
    except Exception as e:
        return jsonify({"error": "Extraction failed: " + str(e)}), 400


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
