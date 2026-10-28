#!/usr/bin/env python3
"""
FourFrames — Letterboxd Taste Compatibility Web Application
100% Free, Zero-Login Letterboxd Taste Comparison & Discovery Engine.
"""

import html
import json
import os
import re
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

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)

# Simple in-memory cache: key -> (timestamp, data)
CACHE = {}
CACHE_TTL_SECONDS = 900  # 15 minutes


def clean_username(raw: str) -> str:
    """Normalize a Letterboxd username or profile URL into a clean slug."""
    if not raw:
        return ""
    s = raw.strip()
    # If full URL was pasted, extract username
    m = re.search(r"letterboxd\.com/([a-zA-Z0-9_-]+)", s, re.IGNORECASE)
    if m:
        return m.group(1).lower()
    s = s.lstrip("@").strip("/").lower()
    s = re.sub(r"[^a-z0-9_-]", "", s)
    return s


def strip_tags(text: str) -> str:
    """Remove HTML tags and unescape entities."""
    if not text:
        return ""
    cleaned = re.sub(r"<[^>]+>", " ", text)
    cleaned = html.unescape(cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def fetch_url(url: str, headers: dict | None = None, timeout: int = 20) -> str:
    """Fetch a URL as UTF-8 text."""
    req_headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,tr;q=0.8",
    }
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, headers=req_headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw_bytes = resp.read()
        return raw_bytes.decode("utf-8", errors="replace")


def fetch_user_rss(username: str) -> dict:
    """
    Fetch and parse a user's public Letterboxd RSS feed:
    https://letterboxd.com/<username>/rss/
    Returns display name, recent watched films, ratings, likes, reviews, and stats.
    """
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
        "dc": "http://purl.org/dc/elements/1.1/",
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
            # Skip non-film items (e.g. lists)
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

        # Extract poster from description HTML
        poster_match = re.search(r'<img\s+src="([^"]+)"', description_html)
        poster_url = poster_match.group(1) if poster_match else ""

        # Extract canonical film slug URL from user's log link
        # e.g. https://letterboxd.com/username/film/after-hours/ -> https://letterboxd.com/film/after-hours/
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

        # Extract written review paragraphs (skipping the <img/> paragraph and "Watched on..." boilerplate)
        paragraphs = re.findall(r"<p>(.*?)</p>", description_html, flags=re.DOTALL)
        review_parts = []
        for p in paragraphs:
            if "<img" in p:
                continue
            plain_p = strip_tags(p)
            if not plain_p:
                continue
            if re.match(r"^Watched on\s+", plain_p, flags=re.IGNORECASE):
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
    """Parse a <div class="poster-grid"> block into a list of film objects."""
    items = []
    cell_pattern = re.compile(
        r'<div class="poster-cell">(.*?)</div>\s*(?=<div class="poster-cell">|</div>)',
        re.DOTALL,
    )
    # Simpler & more reliable: match each <a class="poster" ...> and optionalfollowing poster-caption
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

        # Extract numeric rating if caption has e.g. "4.5★"
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
    """Parse <table class="data-table"> of films two users disagree on."""
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

        # Extract year if formatted as "Title (2019)"
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
    """
    Fetch deep lifetime watch & rating compatibility for two Letterboxd users.
    """
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

    # Check if there is an error message or no score-num
    score_m = re.search(r'<span class="score-num">\s*(\d+)', frag)
    if not score_m:
        err_m = re.search(r'<p class="error[^"]*">(.*?)</p>', frag, re.DOTALL)
        if err_m:
            return {"error": strip_tags(err_m.group(1))}
        return None

    score = int(score_m.group(1))

    copy_m = re.search(
        r'<div class="score-copy">\s*<strong>(.*?)</strong>\s*<span class="muted">(.*?)</span>',
        frag,
        re.DOTALL,
    )
    score_label = strip_tags(copy_m.group(1)) if copy_m else "Taste Match"
    score_summary = strip_tags(copy_m.group(2)) if copy_m else ""

    # Parse user cards
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

    # Parse overlap blocks (<div class="compat-overlap">)
    overlaps = re.findall(r'<div class="compat-overlap">(.*?)</div>\s*(?=<h3>|<p|<div|$)', frag, re.DOTALL)
    # Wait: compat-overlap contains inner <div><span class="big">N</span>...</div>, so let's match outer block properly
    overlap_Matches = re.findall(
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

    if len(overlap_Matches) >= 1:
        o1 = overlap_Matches[0]
        watch_overlap = {
            "onlyUser1": int(o1[0]),
            "bothSeen": int(o1[2]),
            "onlyUser2": int(o1[4]),
        }

    if len(overlap_Matches) >= 2:
        o2 = overlap_Matches[1]
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

    # Parse all <h3> sections
    sections = re.split(r"<h3>(.*?)</h3>", frag, flags=re.DOTALL)
    # sections[0] is before first h3, then pairs of (heading, content)
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
    """
    If deep history isn't available yet, compute compatibility directly from both users' RSS feeds.
    """
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

    avg_dist = round(sum(diffs) / len(diffs), 2) if diffs else 0.6
    base_score = max(15, min(98, round((1 - (avg_dist / 3.5)) * 85 + min(15, both_seen * 2))))

    u1_favs = [
        {
            "title": f["title"],
            "filmUrl": f["filmUrl"],
            "posterUrl": f["posterUrl"],
            "caption": f"{f['rating']}★" if f.get("rating") else "❤️",
            "rating": f.get("rating"),
        }
        for slug, f in u1_films.items()
        if slug not in shared_slugs and ((f.get("rating") or 0) >= 4.0 or f.get("liked"))
    ][:12]

    u2_favs = [
        {
            "title": f["title"],
            "filmUrl": f["filmUrl"],
            "posterUrl": f["posterUrl"],
            "caption": f"{f['rating']}★" if f.get("rating") else "❤️",
            "rating": f.get("rating"),
        }
        for slug, f in u2_films.items()
        if slug not in shared_slugs and ((f.get("rating") or 0) >= 4.0 or f.get("liked"))
    ][:12]

    return {
        "source": "rss_live",
        "score": base_score,
        "scoreLabel": "Recent Activity Match",
        "scoreSummary": f"Computed from recent Letterboxd RSS logs ({both_seen} shared recent films).",
        "users": [
            {
                "username": u1_rss["username"],
                "profileUrl": u1_rss["profileUrl"],
                "avatarUrl": "",
                "watches": u1_rss["recentStats"]["count"],
                "ratings": u1_rss["recentStats"]["ratedCount"],
                "avgRating": u1_rss["recentStats"]["avgRating"],
                "statsText": f"{u1_rss['recentStats']['count']} recent watches · {u1_rss['recentStats']['avgRating']}★ avg",
            },
            {
                "username": u2_rss["username"],
                "profileUrl": u2_rss["profileUrl"],
                "avatarUrl": "",
                "watches": u2_rss["recentStats"]["count"],
                "ratings": u2_rss["recentStats"]["ratedCount"],
                "avgRating": u2_rss["recentStats"]["avgRating"],
                "statsText": f"{u2_rss['recentStats']['count']} recent watches · {u2_rss['recentStats']['avgRating']}★ avg",
            },
        ],
        "watchOverlap": {
            "onlyUser1": only_u1,
            "bothSeen": both_seen,
            "onlyUser2": only_u2,
        },
        "ratingOverlap": {
            "bothRatedCount": len(diffs),
            "user1Higher": u1_higher,
            "agreedExactly": agreed_exact,
            "user2Higher": u2_higher,
            "avgDistance": avg_dist,
        },
        "agreements": sorted(agreements, key=lambda x: x.get("rating") or 0, reverse=True),
        "disagreements": sorted(disagreements, key=lambda x: x.get("diff") or 0, reverse=True),
        "user1FavouritesUnseen": u1_favs,
        "user2FavouritesUnseen": u2_favs,
        "sharedWatchlist": [],
        "recommendations": [],
    }


def build_icebreakers(user1: str, user2: str, data: dict) -> list[dict]:
    """Generate dynamic conversation starters from real compatibility data."""
    icebreakers = []

    agreements = data.get("agreements") or []
    disagreements = data.get("disagreements") or []
    watchlist = data.get("sharedWatchlist") or []
    recommendations = data.get("recommendations") or []
    u1_unseen = data.get("user1FavouritesUnseen") or []
    u2_unseen = data.get("user2FavouritesUnseen") or []

    # 1. Shared Favorite Icebreaker
    if agreements:
        top_agree = agreements[0]
        rating_txt = f" ({top_agree['caption']})" if top_agree.get("caption") else ""
        icebreakers.append(
            {
                "category": "Ortak Favori • Shared Obsession",
                "badgeColor": "green",
                "title": top_agree["title"],
                "prompt": f"İkimiz de {top_agree['title']}{rating_txt} konusunda hemfikiriz! Bu filmi senin için özel kılan en unutulmaz sahne hangisiydi?",
            }
        )

    # 2. Hot Take / Clash Icebreaker
    if disagreements:
        top_clash = disagreements[0]
        icebreakers.append(
            {
                "category": "Zıt Görüş • Hot Take Münazarası",
                "badgeColor": "orange",
                "title": f"{top_clash['title']} (Δ {top_clash['diff']}★)",
                "prompt": f"{top_clash['title']} filmine @{user1} {top_clash['user1Rating']}★ verirken @{user2} {top_clash['user2Rating']}★ vermiş! Karşı tarafı kendi puanına ikna etmek için tek bir argüman hakkın var.",
            }
        )

    # 3. Movie Night / Watchlist or Blind Spot Icebreaker
    if watchlist:
        pick = watchlist[0]
        icebreakers.append(
            {
                "category": "Ortak Watchlist • Movie Night",
                "badgeColor": "blue",
                "title": pick["title"],
                "prompt": f"İkinizin de izleme listesinde (Watchlist) {pick['title']} dahil {len(watchlist)} ortak film bekliyor! Bu hafta sonu beraber izleyip Letterboxd'da loglamaya ne dersiniz?",
            }
        )
    elif recommendations:
        pick = recommendations[0]
        icebreakers.append(
            {
                "category": "Ortak Öneri • Double Feature",
                "badgeColor": "blue",
                "title": pick["title"],
                "prompt": f"Zevk algoritması ikinizin de {pick['title']} filmine bayılacağını söylüyor. Sıradaki film gecesi için listeye ekleyelim mi?",
            }
        )
    elif u1_unseen and u2_unseen:
        icebreakers.append(
            {
                "category": "Film Takası • Blind Spot Trade",
                "badgeColor": "blue",
                "title": f"{u1_unseen[0]['title']} ⇄ {u2_unseen[0]['title']}",
                "prompt": f"Film takası yapalım: Sen benim favorilerimden {u1_unseen[0]['title']} filmini izle, ben de senin favorilerinden {u2_unseen[0]['title']} filmini izleyeyim!",
            }
        )

    return icebreakers


def get_compatibility_payload(user1_raw: str, user2_raw: str, refresh: bool = False) -> dict:
    """Orchestrate parallel fetching of deep compatibility and live RSS feeds."""
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
        raise ValueError(f"Letterboxd üzerinde '@{user1}' kullanıcısı bulunamadı veya profili gizli.")
    if not rss2.get("rssAvailable") and (not deep_data or "error" in deep_data):
        raise ValueError(f"Letterboxd üzerinde '@{user2}' kullanıcısı bulunamadı veya profili gizli.")

    if not deep_data or "error" in deep_data:
        base = compute_rss_fallback(rss1, rss2)
    else:
        base = deep_data

    # Enrich users array with RSS display name & recent stats
    rss_map = {user1: rss1, user2: rss2}
    enriched_users = []
    for idx, u_Name in enumerate([user1, user2]):
        u_card = (
            base["users"][idx]
            if idx < len(base.get("users", []))
            else {
                "username": u_Name,
                "profileUrl": f"https://letterboxd.com/{u_Name}/",
                "avatarUrl": "",
                "watches": 0,
                "ratings": 0,
                "avgRating": 0.0,
            }
        )
        r_data = rss_map[u_Name]
        u_card["displayName"] = r_data.get("displayName") or u_card.get("username") or u_Name
        u_card["recentStats"] = r_data.get("recentStats", {})
        u_card["recentFilms"] = r_data.get("recentFilms", [])[:12]
        u_card["recentReviews"] = r_data.get("recentReviews", [])[:6]
        enriched_users.append(u_card)

    base["users"] = enriched_users

    # Sub-metrics calculation for clean visual breakdown
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

    # Strip internal allRssFilms before caching/returning
    CACHE[cache_key] = (now, base)
    return base


class FourFramesHandler(SimpleHTTPRequestHandler):
    """HTTP Request Handler serving static files and JSON API endpoints."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    def send_json(self, payload: dict, status: int = 200):
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)

        if parsed.path == "/api/compatibility":
            params = urllib.parse.parse_qs(parsed.query)
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

        if parsed.path == "/api/user":
            params = urllib.parse.parse_qs(parsed.query)
            uname = clean_username((params.get("username") or [""])[0])
            if not uname:
                self.send_json({"ok": False, "error": "Kullanıcı adı gerekli."}, status=400)
                return
            rss_data = fetch_user_rss(uname)
            rss_data.pop("allRssFilms", None)
            if not rss_data.get("rssAvailable"):
                self.send_json(
                    {"ok": False, "error": f"@{uname} bulunamadı veya RSS akışı kapalı."},
                    status=404,
                )
                return
            self.send_json({"ok": True, "data": rss_data})
            return

        return super().do_GET()


def main():
    port = int(os.environ.get("PORT", "8000"))
    server = ThreadingHTTPServer(("0.0.0.0", port), FourFramesHandler)
    print(f"FourFrames Web Server running at http://localhost:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server...")
        server.server_close()


if __name__ == "__main__":
    main()
