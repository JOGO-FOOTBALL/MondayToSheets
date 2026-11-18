"""Instagram post metrics from the data science database (socials_analytics), looked up by post link."""

import logging
import re
from datetime import datetime

import psycopg2
import psycopg2.extras

from src import config

log = logging.getLogger(__name__)

# The shortcode in instagram.com/p/<code>/, /reel/<code>/, /tv/<code>/ (optionally with a username first).
_SHORTCODE = re.compile(r"instagram\.com/(?:[^/?#]+/)?(?:p|reels?|tv)/([A-Za-z0-9_-]+)", re.I)
_SQL_SHORTCODE = r"substring(permalink from '/(?:p|reels?|tv)/([A-Za-z0-9_-]+)')"

# Our own posts, plus posts by other accounts where ours is a collaborator (those have no reach).
_QUERY = f"""
    SELECT {_SQL_SHORTCODE} AS shortcode, likes, comments, saved, shares, reposts, reach, views,
           thumbnail_url_abs, fetched_at
    FROM socials_analytics.instagram_posts
    WHERE {_SQL_SHORTCODE} = ANY(%(codes)s)
    UNION ALL
    SELECT {_SQL_SHORTCODE}, likes, comments, saved, shares, reposts, NULL, views,
           thumbnail_url_abs, fetched_at
    FROM socials_analytics.instagram_collab_posts
    WHERE {_SQL_SHORTCODE} = ANY(%(codes)s)
"""


def shortcode(link):
    match = _SHORTCODE.search(link or "")
    return match.group(1) if match else None


def fetch_post_metrics(links):
    """{shortcode: {views, reach, likes, ..., interactions, engagement_rate}} for the given post links."""
    codes = sorted({code for code in map(shortcode, links) if code})
    if not codes:
        return {}

    conn = psycopg2.connect(**config.dsdb_login(), sslmode="require", connect_timeout=15)
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(_QUERY, {"codes": codes})
            rows = cur.fetchall()
    finally:
        conn.close()

    metrics = {}
    for row in sorted(rows, key=lambda r: r["fetched_at"] or datetime.min):  # newest wins
        counts = [row[k] for k in ("likes", "comments", "saved", "shares") if row[k] is not None]
        row["interactions"] = sum(counts) if counts else None
        row["engagement_rate"] = round(row["interactions"] / row["reach"], 4) if counts and row["reach"] else None
        metrics[row["shortcode"]] = row

    log.info("Database: found %d of %d posts", len(metrics), len(codes))
    return metrics
