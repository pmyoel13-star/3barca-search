from flask import Flask, request, jsonify, render_template
from collections import deque
from urllib.parse import urljoin, urlparse
import requests
import sqlite3
import datetime
import re
import os

app = Flask(__name__)

# =============================================
# KONFIGURASI API KEY
# =============================================
SERPAPI_KEY = os.environ.get("SERPAPI_KEY", "ISI_API_KEY_KAMU_DI_SINI")

# =============================================
# SETUP DATABASE
# =============================================
def init_db():
    conn = sqlite3.connect("history.db")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS history (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            query     TEXT NOT NULL,
            timestamp TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()

# =============================================
# ROUTES
# =============================================

@app.route("/")
def home():
    return render_template("index.html")


@app.route("/search")
def search():
    query = request.args.get("q", "").strip()
    if not query:
        return jsonify({"error": "Query kosong!"}), 400

    save_history(query)

    try:
        response = requests.get("https://serpapi.com/search", params={
            "q": query, "api_key": SERPAPI_KEY,
            "hl": "id", "gl": "id", "num": 10
        }, timeout=10)

        data = response.json()
        results = []
        for item in data.get("organic_results", []):
            results.append({
                "title":   item.get("title", ""),
                "link":    item.get("link", ""),
                "snippet": item.get("snippet", "")
            })
        return jsonify({"query": query, "results": results, "total": len(results)})

    except Exception as e:
        return jsonify({"error": f"Gagal mengambil hasil: {str(e)}"}), 500


# =============================================
# ALGORITMA BFS CRAWLER
# =============================================
@app.route("/bfs-crawl")
def bfs_crawl():
    start_url = request.args.get("url", "").strip()
    max_pages  = min(int(request.args.get("max", 10)), 20)

    if not start_url:
        return jsonify({"error": "URL kosong!"}), 400
    if not start_url.startswith("http"):
        start_url = "https://" + start_url

    domain = urlparse(start_url).netloc

    queue   = deque()
    visited = set()
    results = []

    queue.append({"url": start_url, "depth": 0})
    visited.add(start_url)

    while queue and len(results) < max_pages:
        current       = queue.popleft()
        current_url   = current["url"]
        current_depth = current["depth"]

        try:
            res = requests.get(current_url, timeout=5, headers={
                "User-Agent": "Mozilla/5.0 (compatible; BarcaSearchBot/1.0)"
            })
            if res.status_code != 200:
                continue

            html  = res.text
            title = extract_title(html)
            links = extract_links(html, current_url, domain)

            results.append({
                "url":         current_url,
                "title":       title,
                "depth":       current_depth,
                "links_found": len(links)
            })

            for link in links:
                if link not in visited:
                    visited.add(link)
                    queue.append({"url": link, "depth": current_depth + 1})

        except Exception:
            continue

    return jsonify({
        "start_url":     start_url,
        "domain":        domain,
        "total_visited": len(results),
        "pages":         results
    })


# =============================================
# RIWAYAT
# =============================================
@app.route("/history")
def history():
    try:
        conn = sqlite3.connect("history.db")
        rows = conn.execute(
            "SELECT query, timestamp FROM history ORDER BY id DESC LIMIT 10"
        ).fetchall()
        conn.close()
        return jsonify([{"query": r[0], "time": r[1]} for r in rows])
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/history/clear", methods=["DELETE"])
def clear_history():
    conn = sqlite3.connect("history.db")
    conn.execute("DELETE FROM history")
    conn.commit()
    conn.close()
    return jsonify({"message": "Riwayat berhasil dihapus!"})


# =============================================
# HELPERS
# =============================================
def save_history(query):
    conn = sqlite3.connect("history.db")
    conn.execute(
        "INSERT INTO history (query, timestamp) VALUES (?, ?)",
        (query, datetime.datetime.now().strftime("%d-%m-%Y %H:%M"))
    )
    conn.commit()
    conn.close()


def extract_title(html):
    match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    if match:
        return re.sub(r"<[^>]+>", "", match.group(1)).strip()
    return "Tanpa Judul"


def extract_links(html, base_url, domain):
    links = []
    for href in re.findall(r'href=["\']([^"\'#?]+)["\']', html):
        full_url = urljoin(base_url, href)
        parsed   = urlparse(full_url)
        if parsed.netloc == domain and parsed.scheme in ("http", "https"):
            links.append(full_url)
    return list(set(links))


# =============================================
# JALANKAN SERVER
# =============================================
if __name__ == "__main__":
    init_db()
    print("BARCA.SEARCH berjalan di http://localhost:5000")
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
