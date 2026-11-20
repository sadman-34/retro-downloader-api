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
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


def search_social_videos(domain_filter, url_pattern, query, limit=6):
    """Fallback video-only search for X and Facebook via DuckDuckGo HTML."""
    ddg_q = urllib.parse.quote_plus(f"{domain_filter} {query}")
    req = urllib.request.Request(
        f"https://html.duckduckgo.com/html/?q={ddg_q}",
        headers=HEADERS
    )
    results = []
    seen = set()
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            body = resp.read().decode("utf-8", errors="ignore")
        # Extract result links and titles
        matches = re.findall(
            r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
            body,
            re.IGNORECASE | re.DOTALL
        )
        for raw_href, raw_title in matches:
            # Unwrap DDG redirect URL if present
            if "uddg=" in raw_href:
                parsed = urllib.parse.parse_qs(urllib.parse.urlparse(raw_href).query)
                real_url = parsed.get("uddg", [""])[0]
            else:
                real_url = html.unescape(raw_href)

            if not real_url or real_url in seen:
                continue
            # Strictly keep video URLs only (exclude photo/text-only pages)
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
        pass
    return results


@app.route("/api/search")
def search():
    site = request.args.get("site", "youtube").strip().lower()
    query = request.args.get("q", "").strip()

    if not query:
        return jsonify({"error": "Enter a search keyword."}), 400

    encoded_q = urllib.parse.quote_plus(query)

    # Video-only search routing per platform
    if site == "youtube":
        search_target = f"ytsearch6:{query}"
    elif site == "pornhub":
        search_target = f"https://www.pornhub.com/video/search?search={encoded_q}"
    elif site == "xnxx":
        search_target = f"https://www.xnxx.com/search/{encoded_q}"
    elif site == "beeg":
        search_target = f"https://beeg.com/search?q={encoded_q}"
    elif site == "x":
        # Strictly X/Twitter status posts (photos/text-only posts fail later at extraction)
        results = search_social_videos(
            "(site:x.com OR site:twitter.com)",
            r"https?://(www\.)?(x|twitter)\.com/[^/]+/status/\d+",
            query
        )
        return jsonify({"results": results})
    elif site == "facebook":
        # Strictly Facebook video/reel/watch URLs (excludes photo/text posts)
        results = search_social_videos(
            "site:facebook.com",
            r"https?://(www\.|m\.)?facebook\.com/(watch|reel/|[^/]+/videos/)",
            query
        )
        return jsonify({"results": results})
    else:
        return jsonify({"error": "Unsupported site selected."}), 400

    ydl_opts = {
        "extract_flat": True,
        "playlistend": 6,
        "quiet": True,
        "no_warnings": True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(search_target, download=False)
            entries = info.get("entries", []) if info else []
            results = []
            for item in entries:
                if not item:
                    continue
                page_url = item.get("url") or item.get("webpage_url")
                if page_url and not page_url.startswith("http"):
                    if site == "youtube":
                        page_url = f"https://www.youtube.com/watch?v={page_url}"
                    elif site == "xnxx":
                        page_url = f"https://www.xnxx.com{page_url}"
                    elif site == "beeg":
                        page_url = f"https://beeg.com{page_url}"

                # Skip non-video items (channels, playlists, photo posts)
                if not page_url or "/channel/" in page_url or "/playlist" in page_url or "/photo" in page_url:
                    continue

                results.append({
                    "title": item.get("title") or "Untitled Video",
                    "url": page_url,
                    "duration": item.get("duration_string") or ""
                })
            return jsonify({"results": results})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


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
            # Reject image-only or non-video entries
            if not info or (info.get("vcodec") == "none" and quality != "audio"):
                return jsonify({"error": "Selected post does not contain a downloadable video."}), 400

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
        return jsonify({"error": "No video found or link unsupported: " + str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
