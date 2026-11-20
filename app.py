from flask import Flask, request, jsonify
from flask_cors import CORS
import urllib.parse
import urllib.request
import json
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


def search_ytdlp_flat(target, site, limit=6):
    ydl_opts = {
        "extract_flat": "in_playlist",
        "playlistend": limit,
        "quiet": True,
        "no_warnings": True,
        "ignoreerrors": True,
        "socket_timeout": 12,
    }
    results = []
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(target, download=False)
            entries = (info or {}).get("entries") or []
            for item in entries:
                if not item:
                    continue
                url = item.get("url") or item.get("webpage_url") or ""
                if url and not url.startswith("http"):
                    if site == "youtube":
                        url = "https://www.youtube.com/watch?v=" + url
                    elif site == "xnxx":
                        url = "https://www.xnxx.com" + (url if url.startswith("/") else "/" + url)
                    elif site == "beeg":
                        url = "https://beeg.com" + (url if url.startswith("/") else "/" + url)

                if not url:
                    continue

                lower_u = url.lower()
                if any(bad in lower_u for bad in ["/channel/", "/@", "/playlist", "/photo", "/photos", "/category/"]):
                    continue

                results.append({
                    "title": item.get("title") or "Untitled Video",
                    "url": url,
                    "duration": format_duration(item.get("duration_string") or item.get("duration")),
                })
                if len(results) >= limit:
                    break
    except Exception:
        return []
    return results


def search_web_videos(query, domain_filter, url_pattern, limit=6):
    """Search for video-only pages via DuckDuckGo Lite/HTML."""
    endpoints = [
        ("https://lite.duckduckgo.com/lite/", {"q": f"{domain_filter} {query}"}),
        ("https://html.duckduckgo.com/html/", {"q": f"{domain_filter} {query}"}),
    ]
    results = []
    seen = set()

    for base_url, params in endpoints:
        data = urllib.parse.urlencode(params).encode("utf-8")
        req = urllib.request.Request(base_url, data=data, headers=HEADERS)
        try:
            with urllib.request.urlopen(req, timeout=12) as resp:
                body = resp.read().decode("utf-8", errors="ignore")
        except Exception:
            continue

        # Match links in both DuckDuckGo Lite and HTML layouts
        links = re.findall(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', body, re.IGNORECASE | re.DOTALL)
        for raw_href, raw_title in links:
            href = html.unescape(raw_href)
            if "uddg=" in href:
                parsed = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
                real_url = parsed.get("uddg", [""])[0]
            else:
                real_url = href

            if not real_url or real_url in seen:
                continue
            if not re.search(url_pattern, real_url, re.IGNORECASE):
                continue

            seen.add(real_url)
            title = re.sub(r"<[^>]+>", "", html.unescape(raw_title)).strip()
            results.append({
                "title": title or "Video Post",
                "url": real_url,
                "duration": "",
            })
            if len(results) >= limit:
                break

        if results:
            break

    return results


@app.route("/")
def home():
    return jsonify({"status": "ok", "service": "retro-downloader-api"})


@app.route("/api/search")
def search():
    site = request.args.get("site", "youtube").strip().lower()
    query = request.args.get("q", "").strip()

    if not query:
        return jsonify({"error": "Enter a search keyword."}), 400

    encoded_q = urllib.parse.quote_plus(query)
    results = []
    note = ""

    if site == "youtube":
        results = search_ytdlp_flat(f"ytsearch6:{query}", "youtube", 6)
        if not results:
            results = search_web_videos(
                query,
                "site:youtube.com/watch",
                r"https?://(www\.|m\.)?(youtube\.com/watch\?v=|youtu\.be/)",
                6,
            )
    elif site == "pornhub":
        results = search_ytdlp_flat(f"https://www.pornhub.com/video/search?search={encoded_q}", "pornhub", 6)
        if not results:
            results = search_web_videos(
                query,
                "site:pornhub.com/view_video.php",
                r"https?://([a-z]+\.)?pornhub\.com/view_video\.php\?viewkey=",
                6,
            )
    elif site == "xnxx":
        results = search_ytdlp_flat(f"https://www.xnxx.com/search/{encoded_q}", "xnxx", 6)
        if not results:
            results = search_web_videos(
                query,
                "site:xnxx.com/video-",
                r"https?://(www\.)?xnxx\.com/video-",
                6,
            )
    elif site == "beeg":
        results = search_ytdlp_flat(f"https://beeg.com/search?q={encoded_q}", "beeg", 6)
        if not results:
            results = search_web_videos(
                query,
                "site:beeg.com",
                r"https?://(www\.)?beeg\.com/[^/?#]+",
                6,
            )
    elif site == "x":
        results = search_web_videos(
            query,
            "(site:x.com OR site:twitter.com)",
            r"https?://(www\.)?(x|twitter)\.com/[^/]+/status/\d+",
            6,
        )
    elif site == "facebook":
        results = search_web_videos(
            query,
            "site:facebook.com",
            r"https?://(www\.|m\.)?facebook\.com/(watch|reel/|[^/]+/videos/)",
            6,
        )
    else:
        return jsonify({"error": "Unsupported site selected."}), 400

    if not results:
        note = f"No video results returned from Render for {site} (site may block cloud search). Paste a direct video link instead."

    return jsonify({"results": results, "note": note})


@app.route("/api/extract")
def extract():
    url = request.args.get("url", "").strip()
    quality = request.args.get("quality", "240p")

    if not url:
        return jsonify({"error": "No URL provided"}), 400

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
        "socket_timeout": 15,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info or (info.get("vcodec") == "none" and quality != "audio"):
                return jsonify({"error": "Selected post does not contain a video."}), 400

            direct_url = info.get("url")
            if not direct_url:
                return jsonify({"error": "Could not find a direct video stream URL."}), 404

            size_bytes = info.get("filesize") or info.get("filesize_approx")
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
