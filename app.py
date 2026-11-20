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
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}


def search_ddg_videos(domain_query, url_pattern, query, limit=6):
    """Search DuckDuckGo HTML for video-only URLs on social platforms."""
    ddg_q = urllib.parse.quote_plus(f"{domain_query} {query}")
    req = urllib.request.Request(
        f"https://html.duckduckgo.com/html/?q={ddg_q}",
        headers=HEADERS
    )
    results = []
    seen = set()
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read().decode("utf-8", errors="ignore")

        matches = re.findall(
            r'<a[^>]*class="[^"]*result__a[^"]*"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
            body,
            re.IGNORECASE | re.DOTALL
        )
        for raw_href, raw_title in matches:
            href_clean = html.unescape(raw_href)
            if "uddg=" in href_clean:
                parsed = urllib.parse.parse_qs(urllib.parse.urlparse(href_clean).query)
                real_url = parsed.get("uddg", [""])[0]
            else:
                real_url = href_clean

            if not real_url or real_url in seen:
                continue
            if not re.search(url_pattern, real_url, re.IGNORECASE):
                continue

            seen.add(real_url)
            clean_title = re.sub(r"<[^>]+>", "", html.unescape(raw_title)).strip()
            results.append({
                "title": clean_title or "Video Post",
                "url": real_url,
                "duration": ""
            })
            if len(results) >= limit:
                break
    except Exception:
        return []
    return results


def search_with_ytdlp(target, site, limit=6):
    """Run flat yt-dlp search safely without crashing on empty/blocked responses."""
    ydl_opts = {
        "extract_flat": True,
        "playlistend": limit,
        "quiet": True,
        "no_warnings": True,
        "ignoreerrors": True,
    }
    results = []
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(target, download=False)
            entries = (info or {}).get("entries") or []
            for item in entries:
                if not item:
                    continue
                page_url = item.get("url") or item.get("webpage_url") or ""
                if page_url and not page_url.startswith("http"):
                    if site == "youtube":
                        page_url = "https://www.youtube.com/watch?v=" + page_url
                    elif site == "xnxx":
                        page_url = "https://www.xnxx.com" + page_url
                    elif site == "beeg":
                        page_url = "https://beeg.com" + page_url

                if not page_url:
                    continue
                lower_u = page_url.lower()
                if "/channel/" in lower_u or "/playlist" in lower_u or "/photo" in lower_u:
                    continue

                dur = item.get("duration_string")
                if not dur and isinstance(item.get("duration"), (int, float)):
                    secs = int(item["duration"])
                    dur = f"{secs // 60}:{secs % 60:02d}"

                results.append({
                    "title": item.get("title") or "Untitled Video",
                    "url": page_url,
                    "duration": dur or ""
                })
                if len(results) >= limit:
                    break
    except Exception:
        return []
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

    if site == "youtube":
        results = search_with_ytdlp(f"ytsearch6:{query}", "youtube", 6)
    elif site == "pornhub":
        results = search_with_ytdlp(f"https://www.pornhub.com/video/search?search={encoded_q}", "pornhub", 6)
    elif site == "xnxx":
        results = search_with_ytdlp(f"https://www.xnxx.com/search/{encoded_q}", "xnxx", 6)
    elif site == "beeg":
        results = search_with_ytdlp(f"https://beeg.com/search?q={encoded_q}", "beeg", 6)
    elif site == "x":
        results = search_ddg_videos(
            "(site:x.com OR site:twitter.com)",
            r"https?://(www\.)?(x|twitter)\.com/[^/]+/status/\d+",
            query,
            6
        )
    elif site == "facebook":
        results = search_ddg_videos(
            "site:facebook.com",
            r"https?://(www\.|m\.)?facebook\.com/(watch|reel/|[^/]+/videos/)",
            query,
            6
        )
    else:
        return jsonify({"error": "Unsupported site selected."}), 400

    return jsonify({"results": results})


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
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info or (info.get("vcodec") == "none" and quality != "audio"):
                return jsonify({"error": "Selected post has no downloadable video."}), 400

            direct_url = info.get("url")
            if not direct_url:
                return jsonify({"error": "Could not find a direct video stream URL."}), 404

            size_bytes = info.get("filesize") or info.get("filesize_approx")
            size_str = f"{round(size_bytes / (1024 * 1024), 1)} MB" if size_bytes else ""

            return jsonify({
                "title": info.get("title", "Video"),
                "quality": quality,
                "size": size_str,
                "download_url": direct_url
            })
    except Exception as e:
        return jsonify({"error": "Extraction failed: " + str(e)}), 400


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
