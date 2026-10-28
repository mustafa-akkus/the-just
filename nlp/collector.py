"""
Real Letterboxd Turkish Review Harvester & Taste Graph Crawler.
Discovers Letterboxd users via taste similarity graphs and harvests genuine Turkish film reviews
directly from public Letterboxd RSS feeds.
"""

import html
import json
import re
import sqlite3
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from nlp.preprocessor import ASPECT_KEYS, is_turkish_review, suggest_aspect_labels

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "the_just.db"
DATA_DIR = BASE_DIR / "data"
JSONL_PATH = DATA_DIR / "tr_letterboxd_absa.jsonl"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)

DEFAULT_TURKISH_SEEDS = [
    "burakgoral",
    "emrevcr",
    "aliercivan",
    "baskasinema",
    "mubiturkiye",
    "kutsalmotor",
]


def strip_html(text: str) -> str:
    if not text:
        return ""
    cleaned = re.sub(r"<[^>]+>", " ", text)
    cleaned = html.unescape(cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def init_nlp_tables():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS turkish_reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guid TEXT UNIQUE NOT NULL,
            username TEXT NOT NULL,
            display_name TEXT DEFAULT '',
            film_title TEXT NOT NULL,
            film_year TEXT DEFAULT '',
            rating REAL,
            liked INTEGER DEFAULT 0,
            watched_date TEXT DEFAULT '',
            log_url TEXT DEFAULT '',
            poster_url TEXT DEFAULT '',
            review_text TEXT NOT NULL,
            clauses_json TEXT DEFAULT '[]',
            labels_json TEXT DEFAULT '{}',
            evidence_json TEXT DEFAULT '{}',
            is_verified INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.commit()
    conn.close()


def discover_similar_letterboxd_users(seed_username: str, limit: int = 25) -> list[str]:
    """
    Expand from a seed Letterboxd username using the taste similarity graph
    to discover other real Letterboxd members.
    """
    url = f"https://letterboxd.tools/tools/similar-users?username={urllib.parse.quote(seed_username)}"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "HX-Request": "true",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = resp.read().decode("utf-8", errors="replace")
    except Exception:
        return []

    found = []
    for m in re.finditer(r'href="https://letterboxd\.com/([a-zA-Z0-9_-]+)/"', body):
        u = m.group(1).strip().lower()
        if u and u != seed_username.lower() and u not in found:
            found.append(u)
            if len(found) >= limit:
                break
    return found


def fetch_turkish_reviews_from_user_rss(username: str) -> list[dict]:
    """
    Fetch a user's Letterboxd RSS feed and extract all genuine Turkish reviews.
    """
    url = f"https://letterboxd.com/{urllib.parse.quote(username)}/rss/"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            xml_text = resp.read().decode("utf-8", errors="replace")
        root = ET.fromstring(xml_text)
    except Exception:
        return []

    ns = {
        "letterboxd": "https://letterboxd.com",
        "tmdb": "https://themoviedb.org",
    }

    channel = root.find("channel")
    if channel is None:
        return []

    ch_title = channel.findtext("title") or ""
    display_name = ch_title.split(" - ", 1)[1].strip() if " - " in ch_title else username

    extracted = []
    for item in channel.findall("item"):
        film_title = item.findtext("letterboxd:filmTitle", default="", namespaces=ns).strip()
        if not film_title:
            continue

        guid = (item.findtext("guid") or "").strip()
        film_year = item.findtext("letterboxd:filmYear", default="", namespaces=ns).strip()
        rating_str = item.findtext("letterboxd:memberRating", default="", namespaces=ns).strip()
        liked_str = item.findtext("letterboxd:memberLike", default="No", namespaces=ns).strip()
        watched_date = item.findtext("letterboxd:watchedDate", default="", namespaces=ns).strip()
        link = (item.findtext("link") or "").strip()
        description_html = item.findtext("description") or ""

        poster_m = re.search(r'<img\s+src="([^"]+)"', description_html)
        poster_url = poster_m.group(1) if poster_m else ""

        paragraphs = re.findall(r"<p>(.*?)</p>", description_html, flags=re.DOTALL)
        review_parts = []
        for p in paragraphs:
            if "<img" in p:
                continue
            plain_p = strip_html(p)
            if not plain_p:
                continue
            if re.match(r"^Watched on\s+", plain_p, flags=re.IGNORECASE):
                continue
            if re.match(r"^This review may contain spoilers", plain_p, flags=re.IGNORECASE):
                continue
            review_parts.append(plain_p)

        review_text = " ".join(review_parts).strip()
        if not is_turkish_review(review_text):
            continue

        rating_val = None
        if rating_str:
            try:
                rating_val = float(rating_str)
            except ValueError:
                rating_val = None

        suggestion = suggest_aspect_labels(review_text, rating_val)

        extracted.append(
            {
                "guid": guid or f"{username}:{film_title}:{watched_date}",
                "username": username,
                "displayName": display_name,
                "filmTitle": film_title,
                "filmYear": film_year,
                "rating": rating_val,
                "liked": 1 if liked_str.lower() == "yes" else 0,
                "watchedDate": watched_date,
                "logUrl": link,
                "posterUrl": poster_url,
                "reviewText": review_text,
                "clauses": suggestion["clauses"],
                "labels": suggestion["labels"],
                "evidence": suggestion["evidence"],
            }
        )

    return extracted


def harvest_from_letterboxd(seed_usernames: list[str] | None = None, expand_graph: bool = True) -> dict:
    """
    Harvest real Turkish reviews from Letterboxd users and save to SQLite.
    """
    init_nlp_tables()
    seeds = [s.strip().lstrip("@").lower() for s in (seed_usernames or DEFAULT_TURKISH_SEEDS) if s.strip()]
    candidate_users = list(dict.fromkeys(seeds))

    if expand_graph and seeds:
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = [pool.submit(discover_similar_letterboxd_users, s, 20) for s in seeds[:4]]
            for fut in futures:
                for u in fut.result():
                    if u not in candidate_users:
                        candidate_users.append(u)

    all_harvested = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(fetch_turkish_reviews_from_user_rss, u): u for u in candidate_users[:45]}
        for fut in futures:
            res = fut.result()
            if res:
                all_harvested.extend(res)

    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    inserted_count = 0

    for item in all_harvested:
        try:
            cur.execute(
                """
                INSERT OR IGNORE INTO turkish_reviews
                (guid, username, display_name, film_title, film_year, rating, liked, watched_date,
                 log_url, poster_url, review_text, clauses_json, labels_json, evidence_json, is_verified)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                """,
                (
                    item["guid"],
                    item["username"],
                    item["displayName"],
                    item["filmTitle"],
                    item["filmYear"],
                    item["rating"],
                    item["liked"],
                    item["watchedDate"],
                    item["logUrl"],
                    item["posterUrl"],
                    item["reviewText"],
                    json.dumps(item["clauses"], ensure_ascii=False),
                    json.dumps(item["labels"], ensure_ascii=False),
                    json.dumps(item["evidence"], ensure_ascii=False),
                ),
            )
            if cur.rowcount > 0:
                inserted_count += 1
        except Exception:
            pass

    conn.commit()
    cur.execute("SELECT COUNT(*) FROM turkish_reviews")
    total_in_db = cur.fetchone()[0]
    conn.close()

    export_dataset_to_jsonl()

    return {
        "scannedUsersCount": len(candidate_users[:45]),
        "scannedUsers": candidate_users[:45],
        "foundTurkishReviews": len(all_harvested),
        "newInserted": inserted_count,
        "totalInDatabase": total_in_db,
    }


def export_dataset_to_jsonl() -> int:
    """Export all collected and labeled Turkish reviews to data/tr_letterboxd_absa.jsonl."""
    init_nlp_tables()
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM turkish_reviews ORDER BY is_verified DESC, id ASC")
    rows = cur.fetchall()
    conn.close()

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(JSONL_PATH, "w", encoding="utf-8") as f:
        for r in rows:
            record = {
                "id": r["id"],
                "guid": r["guid"],
                "username": r["username"],
                "film_title": r["film_title"],
                "film_year": r["film_year"],
                "rating": r["rating"],
                "review_text": r["review_text"],
                "clauses": json.loads(r["clauses_json"] or "[]"),
                "labels": json.loads(r["labels_json"] or "{}"),
                "is_verified": bool(r["is_verified"]),
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return len(rows)
