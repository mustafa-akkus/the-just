#!/usr/bin/env python3
"""
The Just — Letterboxd Taste Compatibility & Social Discovery Platform
Backend HTTP & REST API Server (Python Standard Library + SQLite3).
"""

import hashlib
import html
import json
import os
import re
import secrets
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
DB_PATH = BASE_DIR / "the_just.db"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)

CACHE = {}
CACHE_TTL_SECONDS = 900
SESSIONS = {}  # token -> user_id


def clean_username(raw: str) -> str:
    if not raw:
        return ""
    s = raw.strip()
    m = re.search(r"letterboxd\.com/([a-zA-Z0-9_-]+)", s, re.IGNORECASE)
    if m:
        return m.group(1).lower()
    s = s.lstrip("@").strip("/").lower()
    return re.sub(r"[^a-z0-9_-]", "", s)


def strip_tags(text: str) -> str:
    if not text:
        return ""
    cleaned = re.sub(r"<[^>]+>", " ", text)
    cleaned = html.unescape(cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def hash_password(password: str, salt: str | None = None) -> str:
    if not salt:
        salt = secrets.token_hex(8)
    digest = hashlib.sha256(f"{salt}:{password}".encode("utf-8")).hexdigest()
    return f"{salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    if not stored or "$" not in stored:
        return False
    salt, _ = stored.split("$", 1)
    return hash_password(password, salt) == stored


def make_avatar_svg_data_uri(initials: str, bg_hex: str = "#1c2632", fg_hex: str = "#00e054") -> str:
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="160" height="160" viewBox="0 0 160 160">'
        f'<rect width="160" height="160" rx="80" fill="{bg_hex}"/>'
        f'<text x="50%" y="53%" dominant-baseline="middle" text-anchor="middle" '
        f'fill="{fg_hex}" font-family="Inter, sans-serif" font-weight="700" font-size="56">{html.escape(initials[:2].upper())}</text>'
        f"</svg>"
    )
    return "data:image/svg+xml;utf8," + urllib.parse.quote(svg)


# ============================================================================
# DATABASE INITIALIZATION & SEEDING
# ============================================================================
def get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            name TEXT NOT NULL,
            age INTEGER DEFAULT 24,
            city TEXT DEFAULT '',
            bio TEXT DEFAULT '',
            intent TEXT DEFAULT 'Both',
            favorite_genres TEXT DEFAULT '',
            letterboxd_username TEXT DEFAULT '',
            photo_data TEXT DEFAULT '',
            lb_summary_json TEXT DEFAULT '{}',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender_id INTEGER NOT NULL,
            receiver_id INTEGER NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    # Check if seed members exist
    cur.execute("SELECT COUNT(*) AS cnt FROM users")
    count = cur.fetchone()["cnt"]
    if count == 0:
        seed_users = [
            {
                "email": "defne@thejust.app",
                "password": "demo123",
                "name": "Defne Yılmaz",
                "age": 26,
                "city": "İstanbul • Kadıköy",
                "bio": "Kurgu asistanı. Wong Kar-wai neonları, 90'lar bağımsız sineması ve festival seçkileri üzerine konuşmayı severim.",
                "intent": "Both",
                "favorite_genres": "Arthouse, Drama, Thriller",
                "letterboxd_username": "karsten",
                "photo_data": make_avatar_svg_data_uri("DY", "#1e293b", "#00e054"),
                "lb_summary": {
                    "watches": 2410,
                    "ratings": 2190,
                    "avgRating": 3.42,
                    "topFilms": ["Mulholland Drive", "Aftersun", "Close-Up", "Parasite"],
                },
            },
            {
                "email": "kaan@thejust.app",
                "password": "demo123",
                "name": "Kaan Demir",
                "age": 28,
                "city": "İstanbul • Beyoğlu",
                "bio": "Sinema yazarı ve yazılım geliştirici. Atlas Sineması çıkışında film tartışacak yeni insanlar arıyorum.",
                "intent": "Friendship",
                "favorite_genres": "Sci-Fi, Neo-Noir, Mystery",
                "letterboxd_username": "davidehrlich",
                "photo_data": make_avatar_svg_data_uri("KD", "#172554", "#40bcf4"),
                "lb_summary": {
                    "watches": 3480,
                    "ratings": 3373,
                    "avgRating": 3.04,
                    "topFilms": ["The Red Shoes", "Children of Men", "Yi Yi", "In the Mood for Love"],
                },
            },
            {
                "email": "zeynep@thejust.app",
                "password": "demo123",
                "name": "Zeynep Kaya",
                "age": 25,
                "city": "Ankara • Çankaya",
                "bio": "Mimarlık yüksek lisans öğrencisi. A24 filmleri, MUBI klasikleri ve psikolojik gerilim tutkunu.",
                "intent": "Dating",
                "favorite_genres": "Indie, Romance, Psychological",
                "letterboxd_username": "dtquandt",
                "photo_data": make_avatar_svg_data_uri("ZK", "#3b0764", "#ff8000"),
                "lb_summary": {
                    "watches": 337,
                    "ratings": 297,
                    "avgRating": 3.88,
                    "topFilms": ["Mulholland Drive", "After Hours", "Poor Things", "The Holdovers"],
                },
            },
            {
                "email": "emre@thejust.app",
                "password": "demo123",
                "name": "Emre Aydın",
                "age": 29,
                "city": "İzmir • Alsancak",
                "bio": "Görüntü yönetmeni. Filmleri senaryodan önce ışık ve renk paletine göre değerlendiririm.",
                "intent": "Both",
                "favorite_genres": "Crime, Classic, World Cinema",
                "letterboxd_username": "schaffrillas",
                "photo_data": make_avatar_svg_data_uri("EA", "#14532d", "#00e054"),
                "lb_summary": {
                    "watches": 1120,
                    "ratings": 1050,
                    "avgRating": 3.56,
                    "topFilms": ["Whiplash", "La Haine", "The Tale of the Princess Kaguya", "Parasite"],
                },
            },
        ]

        for su in seed_users:
            cur.execute(
                """
                INSERT INTO users (email, password_hash, name, age, city, bio, intent, favorite_genres, letterboxd_username, photo_data, lb_summary_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    su["email"],
                    hash_password(su["password"]),
                    su["name"],
                    su["age"],
                    su["city"],
                    su["bio"],
                    su["intent"],
                    su["favorite_genres"],
                    su["letterboxd_username"],
                    su["photo_data"],
                    json.dumps(su["lb_summary"], ensure_ascii=False),
                ),
            )

    conn.commit()
    conn.close()


# ============================================================================
# LETTERBOXD DATA FETCHING & PARSING
# ============================================================================
def fetch_url(url: str, headers: dict | None = None, timeout: int = 20) -> str:
    req_headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,tr;q=0.8",
    }
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, headers=req_headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def fetch_user_rss(username: str) -> dict:
    url = f"https://letterboxd.com/{urllib.parse.quote(username)}/rss/"
    result = {
        "username": username,
        "displayName": username,
        "profileUrl": f"https://letterboxd.com/{username}/",
        "rssAvailable": False,
        "recentFilms": [],
        "recentReviews": [],
        "recentStats": {
            "count": 0,
            "ratedCount": 0,
            "avgRating": 0.0,
            "likedCount": 0,
            "likeRatio": 0,
            "rewatchCount": 0,
        },
    }

    try:
        xml_text = fetch_url(url, timeout=15)
        root = ET.fromstring(xml_text)
    except Exception as exc:
        result["error"] = str(exc)
        return result

    ns = {
        "letterboxd": "https://letterboxd.com",
        "tmdb": "https://themoviedb.org",
    }

    channel = root.find("channel")
    if channel is None:
        return result

    result["rssAvailable"] = True
    ch_title = channel.findtext("title") or ""
    if " - " in ch_title:
        result["displayName"] = ch_title.split(" - ", 1)[1].strip()

    films = []
    reviews = []
    ratings_list = []
    liked_count = 0
    rewatch_count = 0

    for item in channel.findall("item"):
        film_title = item.findtext("letterboxd:filmTitle", default="", namespaces=ns).strip()
        if not film_title:
            continue

        film_year = item.findtext("letterboxd:filmYear", default="", namespaces=ns).strip()
        rating_str = item.findtext("letterboxd:memberRating", default="", namespaces=ns).strip()
        liked_str = item.findtext("letterboxd:memberLike", default="No", namespaces=ns).strip()
        rewatch_str = item.findtext("letterboxd:rewatch", default="No", namespaces=ns).strip()
        watched_date = item.findtext("letterboxd:watchedDate", default="", namespaces=ns).strip()
        tmdb_id = item.findtext("tmdb:movieId", default="", namespaces=ns).strip()
        link = (item.findtext("link") or "").strip()
        guid = (item.findtext("guid") or "").strip()
        description_html = item.findtext("description") or ""

        poster_match = re.search(r'<img\s+src="([^"]+)"', description_html)
        poster_url = poster_match.group(1) if poster_match else ""

        film_url = re.sub(r"letterboxd\.com/[^/]+/film/", "letterboxd.com/film/", link)
        slug_match = re.search(r"/film/([^/]+)/?", film_url)
        film_slug = slug_match.group(1) if slug_match else film_title.lower()

        rating_val = None
        if rating_str:
            try:
                rating_val = float(rating_str)
                ratings_list.append(rating_val)
            except ValueError:
                rating_val = None

        liked = liked_str.lower() == "yes"
        rewatch = rewatch_str.lower() == "yes"
        if liked:
            liked_count += 1
        if rewatch:
            rewatch_count += 1

        paragraphs = re.findall(r"<p>(.*?)</p>", description_html, flags=re.DOTALL)
        review_parts = []
        for p in paragraphs:
            if "<img" in p:
                continue
            plain_p = strip_tags(p)
            if not plain_p or re.match(r"^Watched on\s+", plain_p, flags=re.IGNORECASE):
                continue
            review_parts.append(plain_p)

        review_text = " ".join(review_parts).strip()
        is_review = "letterboxd-review-" in guid or bool(review_text)

        entry = {
            "title": film_title,
            "year": film_year,
            "slug": film_slug,
            "rating": rating_val,
            "liked": liked,
            "rewatch": rewatch,
            "watchedDate": watched_date,
            "tmdbId": tmdb_id,
            "posterUrl": poster_url,
            "filmUrl": film_url,
            "logUrl": link,
            "review": review_text,
        }
        films.append(entry)
        if is_review and review_text:
            reviews.append(entry)

    total_count = len(films)
    rated_count = len(ratings_list)
    avg_rating = round(sum(ratings_list) / rated_count, 2) if rated_count else 0.0
    like_ratio = round((liked_count / total_count) * 100) if total_count else 0

    result["recentFilms"] = films[:24]
    result["allRssFilms"] = films
    result["recentReviews"] = reviews[:10]
    result["recentStats"] = {
        "count": total_count,
        "ratedCount": rated_count,
        "avgRating": avg_rating,
        "likedCount": liked_count,
        "likeRatio": like_ratio,
        "rewatchCount": rewatch_count,
    }
    return result


def parse_poster_grid(grid_html: str) -> list[dict]:
    items = []
    poster_blocks = re.split(r'<div class="poster-cell">', grid_html)[1:]
    for block in poster_blocks:
        link_m = re.search(r'<a class="poster"\s+href="([^"]+)"', block)
        img_m = re.search(r'<img[^>]+src="([^"]+)"[^>]*alt="([^"]*)"', block)
        cap_m = re.search(r'<div class="poster-caption">(.*?)</div>', block, re.DOTALL)

        if not link_m or not img_m:
            continue

        film_url = html.unescape(link_m.group(1).strip())
        poster_url = html.unescape(img_m.group(1).strip())
        title = html.unescape(img_m.group(2).strip())
        caption = strip_tags(cap_m.group(1)) if cap_m else ""

        rating_val = None
        if caption:
            num_m = re.search(r"(\d+(?:\.\d+)?)", caption)
            if num_m:
                try:
                    rating_val = float(num_m.group(1))
                except ValueError:
                    pass

        items.append(
            {
                "title": title,
                "filmUrl": film_url,
                "posterUrl": poster_url,
                "caption": caption,
                "rating": rating_val,
            }
        )
    return items


def parse_disagreements_table(table_html: str) -> list[dict]:
    rows = []
    tbody_m = re.search(r"<tbody>(.*?)</tbody>", table_html, re.DOTALL)
    if not tbody_m:
        return rows

    for tr_m in re.finditer(r"<tr>(.*?)</tr>", tbody_m.group(1), re.DOTALL):
        tds = re.findall(r"<td[^>]*>(.*?)</td>", tr_m.group(1), re.DOTALL)
        if len(tds) < 3:
            continue
        raw_film = strip_tags(tds[0])
        raw_u1 = strip_tags(tds[1])
        raw_u2 = strip_tags(tds[2])

        year = ""
        title = raw_film
        ym = re.match(r"^(.*?)\s*\((\d{4})\)$", raw_film)
        if ym:
            title = ym.group(1).strip()
            year = ym.group(2)

        def parse_star(s: str) -> float:
            m = re.search(r"(\d+(?:\.\d+)?)", s)
            return float(m.group(1)) if m else 0.0

        r1 = parse_star(raw_u1)
        r2 = parse_star(raw_u2)
        diff = round(abs(r1 - r2), 1)

        rows.append(
            {
                "title": title,
                "year": year,
                "user1Rating": r1,
                "user2Rating": r2,
                "diff": diff,
            }
        )
    return rows


def fetch_deep_compatibility(user1: str, user2: str, refresh: bool = False) -> dict | None:
    qs = urllib.parse.urlencode({"user1": user1, "user2": user2})
    url = f"https://letterboxd.tools/tools/compatibility?{qs}"

    try:
        headers = {"HX-Request": "true"}
        if refresh:
            req_data = urllib.parse.urlencode(
                {"user1": user1, "user2": user2, "refresh": "on"}
            ).encode("utf-8")
            req = urllib.request.Request(
                "https://letterboxd.tools/tools/compatibility",
                data=req_data,
                headers={
                    "User-Agent": USER_AGENT,
                    "HX-Request": "true",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=25) as resp:
                frag = resp.read().decode("utf-8", errors="replace")
        else:
            frag = fetch_url(url, headers=headers, timeout=25)
    except Exception:
        return None

    score_m = re.search(r'<span class="score-num">\s*(\d+)', frag)
    if not score_m:
        return None

    score = int(score_m.group(1))
    copy_m = re.search(
        r'<div class="score-copy">\s*<strong>(.*?)</strong>\s*<span class="muted">(.*?)</span>',
        frag,
        re.DOTALL,
    )
    score_label = strip_tags(copy_m.group(1)) if copy_m else "Taste Match"
    score_summary = strip_tags(copy_m.group(2)) if copy_m else ""

    user_cards = []
    for um in re.finditer(
        r'<a class="compat-user"\s+href="([^"]+)"[^>]*>\s*<img\s+src="([^"]+)"[^>]*alt="([^"]*)"[^>]*>\s*<strong>(.*?)</strong>\s*<span class="muted">(.*?)</span>\s*</a>',
        frag,
        re.DOTALL,
    ):
        prof_url = html.unescape(um.group(1).strip())
        avatar_url = html.unescape(um.group(2).strip())
        uname = strip_tags(um.group(4))
        stats_raw = strip_tags(um.group(5))

        watches_m = re.search(r"(\d+)\s*watches", stats_raw)
        ratings_m = re.search(r"(\d+)\s*ratings", stats_raw)
        avg_m = re.search(r"(\d+(?:\.\d+)?)★?\s*avg", stats_raw)

        user_cards.append(
            {
                "username": uname,
                "profileUrl": prof_url,
                "avatarUrl": avatar_url,
                "watches": int(watches_m.group(1)) if watches_m else 0,
                "ratings": int(ratings_m.group(1)) if ratings_m else 0,
                "avgRating": float(avg_m.group(1)) if avg_m else 0.0,
                "statsText": stats_raw,
            }
        )

    overlap_matches = re.findall(
        r'<div class="compat-overlap">\s*<div><span class="big">(\d+)</span><br>(.*?)</div>\s*<div><span class="big">(\d+)</span><br>(.*?)</div>\s*<div><span class="big">(\d+)</span><br>(.*?)</div>\s*</div>',
        frag,
        re.DOTALL,
    )

    watch_overlap = {"onlyUser1": 0, "bothSeen": 0, "onlyUser2": 0}
    rating_overlap = {
        "bothRatedCount": 0,
        "user1Higher": 0,
        "agreedExactly": 0,
        "user2Higher": 0,
        "avgDistance": 0.0,
    }

    if len(overlap_matches) >= 1:
        o1 = overlap_matches[0]
        watch_overlap = {
            "onlyUser1": int(o1[0]),
            "bothSeen": int(o1[2]),
            "onlyUser2": int(o1[4]),
        }

    if len(overlap_matches) >= 2:
        o2 = overlap_matches[1]
        rating_overlap["user1Higher"] = int(o2[0])
        rating_overlap["agreedExactly"] = int(o2[2])
        rating_overlap["user2Higher"] = int(o2[4])

    both_rated_m = re.search(r"Of the\s+(\d+)\s+films you've both rated", frag, re.IGNORECASE)
    if both_rated_m:
        rating_overlap["bothRatedCount"] = int(both_rated_m.group(1))
    else:
        rating_overlap["bothRatedCount"] = (
            rating_overlap["user1Higher"]
            + rating_overlap["agreedExactly"]
            + rating_overlap["user2Higher"]
        )

    dist_m = re.search(r"Average rating distance:\s*(\d+(?:\.\d+)?)", frag, re.IGNORECASE)
    if dist_m:
        rating_overlap["avgDistance"] = float(dist_m.group(1))
    else:
        dist_m2 = re.search(r"rate them\s*(\d+(?:\.\d+)?)★?\s*apart", score_summary, re.IGNORECASE)
        if dist_m2:
            rating_overlap["avgDistance"] = float(dist_m2.group(1))

    sections = re.split(r"<h3>(.*?)</h3>", frag, flags=re.DOTALL)
    user1_favs_unseen = []
    user2_favs_unseen = []
    agreements = []
    disagreements = []
    shared_watchlist = []
    recommendations = []

    for i in range(1, len(sections) - 1, 2):
        heading = strip_tags(sections[i]).lower()
        body = sections[i + 1]

        if "favourites" in heading and "hasn't seen" in heading:
            if heading.startswith(user1.lower()):
                user1_favs_unseen = parse_poster_grid(body)
            else:
                user2_favs_unseen = parse_poster_grid(body)
        elif "films you agree on" in heading:
            agreements = parse_poster_grid(body)
        elif "films you disagree most on" in heading:
            disagreements = parse_disagreements_table(body)
        elif "watchlists" in heading:
            shared_watchlist = parse_poster_grid(body)
        elif "model thinks you'll both like" in heading:
            recommendations = parse_poster_grid(body)

    return {
        "source": "deep_history",
        "score": score,
        "scoreLabel": score_label,
        "scoreSummary": score_summary,
        "users": user_cards,
        "watchOverlap": watch_overlap,
        "ratingOverlap": rating_overlap,
        "agreements": agreements,
        "disagreements": disagreements,
        "user1FavouritesUnseen": user1_favs_unseen,
        "user2FavouritesUnseen": user2_favs_unseen,
        "sharedWatchlist": shared_watchlist,
        "recommendations": recommendations,
    }


def compute_rss_fallback(u1_rss: dict, u2_rss: dict) -> dict:
    u1_films = {f["slug"]: f for f in u1_rss.get("allRssFilms", [])}
    u2_films = {f["slug"]: f for f in u2_rss.get("allRssFilms", [])}

    shared_slugs = set(u1_films.keys()) & set(u2_films.keys())
    only_u1 = len(set(u1_films.keys()) - shared_slugs)
    only_u2 = len(set(u2_films.keys()) - shared_slugs)
    both_seen = len(shared_slugs)

    agreements = []
    disagreements = []
    u1_higher = 0
    u2_higher = 0
    agreed_exact = 0
    diffs = []

    for slug in shared_slugs:
        f1 = u1_films[slug]
        f2 = u2_films[slug]
        r1 = f1.get("rating")
        r2 = f2.get("rating")
        if r1 is not None and r2 is not None:
            diff = abs(r1 - r2)
            diffs.append(diff)
            if diff == 0:
                agreed_exact += 1
            elif r1 > r2:
                u1_higher += 1
            else:
                u2_higher += 1

            avg_r = round((r1 + r2) / 2, 1)
            if diff <= 0.5 and avg_r >= 3.5:
                agreements.append(
                    {
                        "title": f1["title"],
                        "filmUrl": f1["filmUrl"],
                        "posterUrl": f1["posterUrl"] or f2["posterUrl"],
                        "caption": f"{avg_r}★",
                        "rating": avg_r,
                    }
                )
            elif diff >= 1.0:
                disagreements.append(
                    {
                        "title": f1["title"],
                        "year": f1["year"],
                        "user1Rating": r1,
                        "user2Rating": r2,
                        "diff": round(diff, 1),
                    }
                )

    avg_dist = round(sum(diffs) / len(diffs), 2) if diffs else 0.65
    base_score = max(35, min(96, round((1 - (avg_dist / 3.5)) * 82 + min(15, both_seen * 3))))

    return {
        "source": "rss_live",
        "score": base_score,
        "scoreLabel": "Taste Compatibility",
        "scoreSummary": f"Computed from Letterboxd activity ({both_seen} shared recent watches).",
        "users": [
            {
                "username": u1_rss["username"],
                "profileUrl": u1_rss["profileUrl"],
                "avatarUrl": "",
                "watches": u1_rss["recentStats"]["count"],
                "ratings": u1_rss["recentStats"]["ratedCount"],
                "avgRating": u1_rss["recentStats"]["avgRating"],
            },
            {
                "username": u2_rss["username"],
                "profileUrl": u2_rss["profileUrl"],
                "avatarUrl": "",
                "watches": u2_rss["recentStats"]["count"],
                "ratings": u2_rss["recentStats"]["ratedCount"],
                "avgRating": u2_rss["recentStats"]["avgRating"],
            },
        ],
        "watchOverlap": {"onlyUser1": only_u1, "bothSeen": both_seen, "onlyUser2": only_u2},
        "ratingOverlap": {
            "bothRatedCount": len(diffs),
            "user1Higher": u1_higher,
            "agreedExactly": agreed_exact,
            "user2Higher": u2_higher,
            "avgDistance": avg_dist,
        },
        "agreements": sorted(agreements, key=lambda x: x.get("rating") or 0, reverse=True),
        "disagreements": sorted(disagreements, key=lambda x: x.get("diff") or 0, reverse=True),
        "user1FavouritesUnseen": [],
        "user2FavouritesUnseen": [],
        "sharedWatchlist": [],
        "recommendations": [],
    }


def build_icebreakers(user1: str, user2: str, data: dict) -> list[dict]:
    icebreakers = []
    agreements = data.get("agreements") or []
    disagreements = data.get("disagreements") or []
    watchlist = data.get("sharedWatchlist") or []
    recommendations = data.get("recommendations") or []

    if agreements:
        top_agree = agreements[0]
        rating_txt = f" ({top_agree['caption']})" if top_agree.get("caption") else ""
        icebreakers.append(
            {
                "category": "Ortak Favori",
                "badgeColor": "green",
                "title": top_agree["title"],
                "prompt": f"İkimiz de {top_agree['title']}{rating_txt} konusunda hemfikiriz! Bu filmi senin için özel kılan sahne hangisiydi?",
            }
        )

    if disagreements:
        top_clash = disagreements[0]
        icebreakers.append(
            {
                "category": "Farklı Görüş",
                "badgeColor": "orange",
                "title": f"{top_clash['title']} (Δ {top_clash['diff']}★)",
                "prompt": f"{top_clash['title']} filmine @{user1} {top_clash['user1Rating']}★ verirken @{user2} {top_clash['user2Rating']}★ vermiş! Karşı tarafı ikna etmek için tek bir cümlen var.",
            }
        )

    if watchlist:
        pick = watchlist[0]
        icebreakers.append(
            {
                "category": "Ortak Watchlist",
                "badgeColor": "blue",
                "title": pick["title"],
                "prompt": f"İkinizin de izleme listesinde {pick['title']} dahil {len(watchlist)} ortak film bekliyor! Beraber izleyip tartışmaya ne dersin?",
            }
        )
    elif recommendations:
        pick = recommendations[0]
        icebreakers.append(
            {
                "category": "Ortak Öneri",
                "badgeColor": "blue",
                "title": pick["title"],
                "prompt": f"Zevk algoritması ikimizin de {pick['title']} filmine bayılacağını söylüyor. Sıradaki film olarak izleyelim mi?",
            }
        )

    return icebreakers


def get_compatibility_payload(user1_raw: str, user2_raw: str, refresh: bool = False) -> dict:
    user1 = clean_username(user1_raw)
    user2 = clean_username(user2_raw)

    if not user1 or not user2:
        raise ValueError("Lütfen geçerli iki Letterboxd kullanıcı adı girin.")
    if user1 == user2:
        raise ValueError("Karşılaştırma yapmak için iki farklı Letterboxd kullanıcı adı girin.")

    cache_key = f"compat:{user1}:{user2}"
    now = time.time()
    if not refresh and cache_key in CACHE:
        ts, cached_val = CACHE[cache_key]
        if now - ts < CACHE_TTL_SECONDS:
            return cached_val

    with ThreadPoolExecutor(max_workers=3) as pool:
        fut_deep = pool.submit(fetch_deep_compatibility, user1, user2, refresh)
        fut_rss1 = pool.submit(fetch_user_rss, user1)
        fut_rss2 = pool.submit(fetch_user_rss, user2)

        deep_data = fut_deep.result()
        rss1 = fut_rss1.result()
        rss2 = fut_rss2.result()

    if not rss1.get("rssAvailable") and (not deep_data or "error" in deep_data):
        raise ValueError(f"Letterboxd üzerinde '@{user1}' kullanıcısı bulunamadı.")
    if not rss2.get("rssAvailable") and (not deep_data or "error" in deep_data):
        raise ValueError(f"Letterboxd üzerinde '@{user2}' kullanıcısı bulunamadı.")

    if not deep_data or "error" in deep_data:
        base = compute_rss_fallback(rss1, rss2)
    else:
        base = deep_data

    rss_map = {user1: rss1, user2: rss2}
    enriched_users = []
    for idx, u_name in enumerate([user1, user2]):
        u_card = (
            base["users"][idx]
            if idx < len(base.get("users", []))
            else {
                "username": u_name,
                "profileUrl": f"https://letterboxd.com/{u_name}/",
                "avatarUrl": "",
                "watches": 0,
                "ratings": 0,
                "avgRating": 0.0,
            }
        )
        r_data = rss_map[u_name]
        u_card["displayName"] = r_data.get("displayName") or u_card.get("username") or u_name
        u_card["recentStats"] = r_data.get("recentStats", {})
        u_card["recentFilms"] = r_data.get("recentFilms", [])[:12]
        u_card["recentReviews"] = r_data.get("recentReviews", [])[:6]
        enriched_users.append(u_card)

    base["users"] = enriched_users

    wo = base["watchOverlap"]
    ro = base["ratingOverlap"]
    avg_dist = ro.get("avgDistance") or 0.8
    both_seen = wo.get("bothSeen") or 0
    both_rated = ro.get("bothRatedCount") or 1
    agreed_exact = ro.get("agreedExactly") or 0

    rating_harmony_pct = max(10, min(100, round((1 - (avg_dist / 3.0)) * 100)))
    exact_match_pct = max(5, min(100, round((agreed_exact / max(1, both_rated)) * 100)))
    min_user_watches = min(
        max(1, enriched_users[0].get("watches") or 1),
        max(1, enriched_users[1].get("watches") or 1),
    )
    catalog_overlap_pct = max(5, min(100, round((both_seen / min_user_watches) * 100)))

    base["subMetrics"] = {
        "ratingHarmony": rating_harmony_pct,
        "catalogOverlap": catalog_overlap_pct,
        "exactAgreementRate": exact_match_pct,
    }

    base["icebreakers"] = build_icebreakers(user1, user2, base)
    base["syncedAt"] = time.strftime("%Y-%m-%d %H:%M:%S")

    CACHE[cache_key] = (now, base)
    return base


def build_user_lb_summary(lb_username: str) -> dict:
    """Fetch a lightweight Letterboxd summary for a user when they register or update profile."""
    uname = clean_username(lb_username)
    if not uname:
        return {"watches": 0, "ratings": 0, "avgRating": 0.0, "topFilms": []}
    rss = fetch_user_rss(uname)
    if not rss.get("rssAvailable"):
        return {"watches": 0, "ratings": 0, "avgRating": 0.0, "topFilms": []}

    films = rss.get("recentFilms", [])
    top_films = [
        f["title"]
        for f in sorted(films, key=lambda x: (x.get("rating") or 0, 1 if x.get("liked") else 0), reverse=True)[:4]
    ]
    return {
        "watches": rss["recentStats"]["count"],
        "ratings": rss["recentStats"]["ratedCount"],
        "avgRating": rss["recentStats"]["avgRating"],
        "topFilms": top_films,
    }


def row_to_user_dict(row: sqlite3.Row) -> dict:
    try:
        lb_sum = json.loads(row["lb_summary_json"] or "{}")
    except Exception:
        lb_sum = {}
    return {
        "id": row["id"],
        "email": row["email"],
        "name": row["name"],
        "age": row["age"],
        "city": row["city"],
        "bio": row["bio"],
        "intent": row["intent"],
        "favoriteGenres": row["favorite_genres"],
        "letterboxdUsername": row["letterboxd_username"],
        "photoData": row["photo_data"] or make_avatar_svg_data_uri(row["name"] or "U"),
        "lbSummary": lb_sum,
    }


# ============================================================================
# HTTP SERVER & API HANDLER
# ============================================================================
class TheJustHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    def send_json(self, payload: dict, status: int = 200):
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()
        self.wfile.write(raw)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()

    def read_json_body(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8", errors="replace")
        return json.loads(raw)

    def get_current_user_row(self):
        auth = self.headers.get("Authorization", "")
        token = auth.replace("Bearer ", "").strip()
        if not token or token not in SESSIONS:
            return None
        uid = SESSIONS[token]
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE id = ?", (uid,))
        row = cur.fetchone()
        conn.close()
        return row

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)

        # 1. REGISTER
        if parsed.path == "/api/auth/register":
            try:
                body = self.read_json_body()
                email = (body.get("email") or "").strip().lower()
                password = body.get("password") or ""
                name = (body.get("name") or "").strip()
                age = int(body.get("age") or 24)
                city = (body.get("city") or "").strip()
                bio = (body.get("bio") or "").strip()
                intent = (body.get("intent") or "Both").strip()
                fav_genres = (body.get("favoriteGenres") or "").strip()
                lb_user = clean_username(body.get("letterboxdUsername") or "")
                photo_data = body.get("photoData") or make_avatar_svg_data_uri(name or "U")

                if not email or not password or not name:
                    self.send_json({"ok": False, "error": "Ad, e-posta ve şifre alanları zorunludur."}, status=400)
                    return

                lb_summary = build_user_lb_summary(lb_user) if lb_user else {}

                conn = get_db()
                cur = conn.cursor()
                try:
                    cur.execute(
                        """
                        INSERT INTO users (email, password_hash, name, age, city, bio, intent, favorite_genres, letterboxd_username, photo_data, lb_summary_json)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            email,
                            hash_password(password),
                            name,
                            age,
                            city,
                            bio,
                            intent,
                            fav_genres,
                            lb_user,
                            photo_data,
                            json.dumps(lb_summary, ensure_ascii=False),
                        ),
                    )
                    conn.commit()
                    uid = cur.lastrowid
                except sqlite3.IntegrityError:
                    conn.close()
                    self.send_json({"ok": False, "error": "Bu e-posta adresi ile kayıtlı bir hesap zaten var."}, status=400)
                    return

                cur.execute("SELECT * FROM users WHERE id = ?", (uid,))
                row = cur.fetchone()
                conn.close()

                token = secrets.token_hex(24)
                SESSIONS[token] = uid
                self.send_json({"ok": True, "token": token, "user": row_to_user_dict(row)})
            except Exception as exc:
                self.send_json({"ok": False, "error": str(exc)}, status=500)
            return

        # 2. LOGIN
        if parsed.path == "/api/auth/login":
            try:
                body = self.read_json_body()
                email = (body.get("email") or "").strip().lower()
                password = body.get("password") or ""

                conn = get_db()
                cur = conn.cursor()
                cur.execute("SELECT * FROM users WHERE lower(email) = ?", (email,))
                row = cur.fetchone()
                conn.close()

                if not row or not verify_password(password, row["password_hash"]):
                    self.send_json({"ok": False, "error": "E-posta veya şifre hatalı."}, status=401)
                    return

                token = secrets.token_hex(24)
                SESSIONS[token] = row["id"]
                self.send_json({"ok": True, "token": token, "user": row_to_user_dict(row)})
            except Exception as exc:
                self.send_json({"ok": False, "error": str(exc)}, status=500)
            return

        # 3. UPDATE PROFILE & PHOTO
        if parsed.path == "/api/profile/update":
            row = self.get_current_user_row()
            if not row:
                self.send_json({"ok": False, "error": "Oturum açmanız gerekiyor."}, status=401)
                return
            try:
                body = self.read_json_body()
                name = (body.get("name") or row["name"]).strip()
                age = int(body.get("age") or row["age"] or 24)
                city = (body.get("city") or "").strip()
                bio = (body.get("bio") or "").strip()
                intent = (body.get("intent") or "Both").strip()
                fav_genres = (body.get("favoriteGenres") or "").strip()
                lb_user = clean_username(body.get("letterboxdUsername") or "")
                photo_data = body.get("photoData") or row["photo_data"]

                lb_summary_json = row["lb_summary_json"]
                if lb_user and lb_user != row["letterboxd_username"]:
                    lb_summary = build_user_lb_summary(lb_user)
                    lb_summary_json = json.dumps(lb_summary, ensure_ascii=False)
                elif lb_user and lb_summary_json in ("", "{}"):
                    lb_summary = build_user_lb_summary(lb_user)
                    lb_summary_json = json.dumps(lb_summary, ensure_ascii=False)

                conn = get_db()
                cur = conn.cursor()
                cur.execute(
                    """
                    UPDATE users
                    SET name = ?, age = ?, city = ?, bio = ?, intent = ?, favorite_genres = ?,
                        letterboxd_username = ?, photo_data = ?, lb_summary_json = ?
                    WHERE id = ?
                    """,
                    (
                        name,
                        age,
                        city,
                        bio,
                        intent,
                        fav_genres,
                        lb_user,
                        photo_data,
                        lb_summary_json,
                        row["id"],
                    ),
                )
                conn.commit()
                cur.execute("SELECT * FROM users WHERE id = ?", (row["id"],))
                updated = cur.fetchone()
                conn.close()

                self.send_json({"ok": True, "user": row_to_user_dict(updated)})
            except Exception as exc:
                self.send_json({"ok": False, "error": str(exc)}, status=500)
            return

        # 4. SEND MESSAGE
        if parsed.path == "/api/messages":
            row = self.get_current_user_row()
            if not row:
                self.send_json({"ok": False, "error": "Oturum açmanız gerekiyor."}, status=401)
                return
            try:
                body = self.read_json_body()
                receiver_id = int(body.get("receiverId") or 0)
                content = (body.get("content") or "").strip()
                if not receiver_id or not content:
                    self.send_json({"ok": False, "error": "Mesaj içeriği boş olamaz."}, status=400)
                    return

                conn = get_db()
                cur = conn.cursor()
                cur.execute(
                    "INSERT INTO messages (sender_id, receiver_id, content) VALUES (?, ?, ?)",
                    (row["id"], receiver_id, content),
                )
                conn.commit()
                conn.close()
                self.send_json({"ok": True})
            except Exception as exc:
                self.send_json({"ok": False, "error": str(exc)}, status=500)
            return

        self.send_json({"ok": False, "error": "Not found"}, status=404)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        # 1. CURRENT USER SESSION
        if parsed.path == "/api/auth/me":
            row = self.get_current_user_row()
            if not row:
                self.send_json({"ok": False, "error": "Oturum bulunamadı."}, status=401)
                return
            self.send_json({"ok": True, "user": row_to_user_dict(row)})
            return

        # 2. DISCOVER COMMUNITY MEMBERS
        if parsed.path == "/api/discover":
            me = self.get_current_user_row()
            my_id = me["id"] if me else 0
            my_lb = (me["letterboxd_username"] if me else "") or "dtquandt"

            conn = get_db()
            cur = conn.cursor()
            cur.execute("SELECT * FROM users WHERE id != ? ORDER BY id ASC", (my_id,))
            rows = cur.fetchall()
            conn.close()

            members = []
            for r in rows:
                m_dict = row_to_user_dict(r)
                other_lb = m_dict["letterboxdUsername"]

                # Compute quick taste compatibility score
                compat_score = 72
                shared_count = 45
                shared_sample = m_dict["lbSummary"].get("topFilms", [])[:3]

                if my_lb and other_lb and my_lb != other_lb:
                    cache_key = f"compat:{my_lb}:{other_lb}"
                    if cache_key in CACHE:
                        _, c_data = CACHE[cache_key]
                        compat_score = c_data.get("score", 72)
                        shared_count = c_data.get("watchOverlap", {}).get("bothSeen", 45)
                        shared_sample = [a["title"] for a in (c_data.get("agreements") or [])[:3]]
                    else:
                        # Deterministic fast preview score until detailed view is opened, or live if cached
                        h = int(hashlib.md5(f"{my_lb}:{other_lb}".encode()).hexdigest()[:4], 16)
                        compat_score = 52 + (h % 41)
                        shared_count = 28 + (h % 120)

                m_dict["compatibility"] = {
                    "score": compat_score,
                    "bothSeen": shared_count,
                    "sharedHighlights": shared_sample,
                }
                members.append(m_dict)

            members.sort(key=lambda x: x["compatibility"]["score"], reverse=True)
            self.send_json({"ok": True, "members": members})
            return

        # 3. SINGLE MEMBER PROFILE + LIVE COMPATIBILITY WITH CURRENT USER
        if parsed.path == "/api/member":
            member_id = int((params.get("id") or ["0"])[0])
            me = self.get_current_user_row()
            my_lb = (me["letterboxd_username"] if me else "") or (params.get("my_lb") or ["dtquandt"])[0]

            conn = get_db()
            cur = conn.cursor()
            cur.execute("SELECT * FROM users WHERE id = ?", (member_id,))
            target = cur.fetchone()
            conn.close()

            if not target:
                self.send_json({"ok": False, "error": "Kullanıcı bulunamadı."}, status=404)
                return

            member_dict = row_to_user_dict(target)
            target_lb = member_dict["letterboxdUsername"]

            compat_data = None
            if my_lb and target_lb and my_lb != target_lb:
                try:
                    compat_data = get_compatibility_payload(my_lb, target_lb, refresh=False)
                except Exception:
                    compat_data = None

            self.send_json({"ok": True, "member": member_dict, "compatibility": compat_data})
            return

        # 4. MESSAGES LIST WITH A MEMBER
        if parsed.path == "/api/messages":
            me = self.get_current_user_row()
            if not me:
                self.send_json({"ok": False, "error": "Oturum açmanız gerekiyor."}, status=401)
                return
            other_id = int((params.get("user_id") or ["0"])[0])
            conn = get_db()
            cur = conn.cursor()
            cur.execute(
                """
                SELECT * FROM messages
                WHERE (sender_id = ? AND receiver_id = ?)
                   OR (sender_id = ? AND receiver_id = ?)
                ORDER BY id ASC
                """,
                (me["id"], other_id, other_id, me["id"]),
            )
            msg_rows = cur.fetchall()
            conn.close()

            messages = [
                {
                    "id": mr["id"],
                    "senderId": mr["sender_id"],
                    "receiverId": mr["receiver_id"],
                    "isMine": mr["sender_id"] == me["id"],
                    "content": mr["content"],
                    "createdAt": mr["created_at"],
                }
                for mr in msg_rows
            ]
            self.send_json({"ok": True, "messages": messages})
            return

        # 5. STANDALONE LETTERBOXD COMPATIBILITY ENDPOINT
        if parsed.path == "/api/compatibility":
            u1 = (params.get("user1") or [""])[0]
            u2 = (params.get("user2") or [""])[0]
            refresh = (params.get("refresh") or ["0"])[0] in ("1", "true", "on")

            try:
                data = get_compatibility_payload(u1, u2, refresh=refresh)
                self.send_json({"ok": True, "data": data})
            except ValueError as ve:
                self.send_json({"ok": False, "error": str(ve)}, status=400)
            except Exception as exc:
                self.send_json(
                    {"ok": False, "error": f"Veri çekilirken bir hata oluştu: {exc}"},
                    status=500,
                )
            return

        return super().do_GET()


def main():
    init_db()
    port = int(os.environ.get("PORT", "8000"))
    server = ThreadingHTTPServer(("0.0.0.0", port), TheJustHandler)
    print(f"The Just Web Server running at http://localhost:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()


if __name__ == "__main__":
    main()
