# Server setup adapted from the FastMCP quickstart in the MCP Python SDK README:
# https://github.com/modelcontextprotocol/python-sdk
import ipaddress
import logging
import socket
import sys
import time
from collections import deque
from pathlib import Path
from urllib.parse import urlparse

import feedparser
import httpx
from bs4 import BeautifulSoup
from dotenv import dotenv_values
from mcp.server.fastmcp import FastMCP
from notion_client import Client
from notion_client.errors import APIResponseError

# Log to stderr: stdout is reserved for the MCP protocol over stdio.
logging.basicConfig(stream=sys.stderr, level=logging.INFO)
log = logging.getLogger("pm-knowledge")

ENV = dotenv_values(Path(__file__).parent / ".env")
notion = Client(auth=ENV["NOTION_TOKEN"])
DATABASE_ID = ENV["NOTION_DATABASE_ID"]

FEEDS = {
    "nngroup": "https://www.nngroup.com/feed/rss/",
    "smashing_ux": "https://www.smashingmagazine.com/categories/ux-design/index.xml",
    "mind_the_product": "https://www.mindtheproduct.com/feed/",
    "ux_collective": "https://uxdesign.cc/feed",
}

ALLOWED_DOMAINS = {"nngroup.com", "smashingmagazine.com", "mindtheproduct.com", "uxdesign.cc"}


class RateLimiter:
    """Sliding-window rate limiter: at most max_calls per period (seconds)."""

    def __init__(self, max_calls: int, period: float):
        self.max_calls = max_calls
        self.period = period
        self.calls = deque()

    def allow(self) -> bool:
        now = time.monotonic()
        # Drop timestamps that have fallen outside the window.
        while self.calls and now - self.calls[0] > self.period:
            self.calls.popleft()
        if len(self.calls) >= self.max_calls:
            return False
        self.calls.append(now)
        return True


notion_limiter = RateLimiter(max_calls=10, period=60)
fetch_limiter = RateLimiter(max_calls=30, period=60)

mcp = FastMCP("pm-knowledge")


@mcp.tool()
def fetch_feed(source: str, limit: int = 10) -> dict:
    """Get recent articles from a curated product management / design source.
    Valid sources: nngroup, smashing_ux, mind_the_product, ux_collective."""
    if source not in FEEDS:
        return {"error": f"Unknown source. Choose from: {', '.join(FEEDS)}"}
    limit = max(1, min(limit, 20))
    try:
        resp = httpx.get(FEEDS[source], timeout=10, follow_redirects=True)
        resp.raise_for_status()
    except httpx.HTTPError:
        log.exception("Feed fetch failed for %s", source)
        return {"error": f"Could not fetch feed '{source}'. Try again later."}
    feed = feedparser.parse(resp.content)
    articles = [
        {
            "title": e.get("title", ""),
            "url": e.get("link", ""),
            "published": e.get("published", ""),
            "summary": e.get("summary", "")[:500],
        }
        for e in feed.entries[:limit]
    ]
    return {"source": source, "articles": articles}


@mcp.tool()
def save_to_notion(title: str, url: str, source: str,
                   skill_areas: list[str], takeaways: str) -> dict:
    """Save one article to the Notion knowledge database.
    skill_areas: short tags like 'user research' or 'prioritization'.
    takeaways: 3-5 concrete takeaways, one per line."""
    if not notion_limiter.allow():
        return {"error": "Rate limit reached: max 10 Notion saves per minute. Try again shortly."}
    try:
        page = notion.pages.create(
            parent={"database_id": DATABASE_ID},
            properties={
                "Name": {"title": [{"text": {"content": title[:200]}}]},
                "URL": {"url": url},
                "Source": {"rich_text": [{"text": {"content": source}}]},
                "Skill Area": {"multi_select": [{"name": s[:100]} for s in skill_areas]},
                "Takeaways": {"rich_text": [{"text": {"content": takeaways[:2000]}}]},
                "Status": {"select": {"name": "Unread"}},
            },
        )
    except APIResponseError:
        log.exception("Notion save failed")
        return {"error": "Could not save to Notion. Check the server log."}
    return {"saved": True, "notion_url": page["url"]}


def is_safe_url(url: str) -> bool:
    """Return True only if url is safe to fetch (SSRF protection)."""
    parsed = urlparse(url)
    hostname = parsed.hostname

    # Check 1: only web schemes, and the URL must have a hostname.
    if parsed.scheme not in ("http", "https"):
        return False
    if not hostname:
        return False

    # Check 2: hostname must be an allowed domain or a subdomain of one.
    allowed = any(
        hostname == domain or hostname.endswith("." + domain)
        for domain in ALLOWED_DOMAINS
    )
    if not allowed:
        return False

    # Check 3: the hostname must not resolve to an internal address.
    try:
        ip = ipaddress.ip_address(socket.gethostbyname(hostname))
    except (socket.gaierror, ValueError):
        return False
    if ip.is_private or ip.is_loopback or ip.is_link_local:
        return False

    return True


@mcp.tool()
def fetch_article(url: str) -> dict:
    """Fetch the readable text of an article from an approved PM/design site."""
    if not fetch_limiter.allow():
        return {"error": "Rate limit reached: max 30 article fetches per minute."}
    if not is_safe_url(url):
        return {"error": "URL not allowed."}
    try:
        resp = httpx.get(url, timeout=10, follow_redirects=False)
        resp.raise_for_status()
    except httpx.HTTPError:
        log.exception("Article fetch failed")
        return {"error": "Could not fetch article."}
    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    text = " ".join(soup.get_text(" ").split())
    return {"url": url, "text": text[:8000]}


@mcp.prompt()
def skill_digest(skill_area: str) -> str:
    """Build a Notion digest of recent articles on one PM/design skill."""
    return f"""Build a learning digest on "{skill_area}".

1. Call fetch_feed for each source: nngroup, smashing_ux, mind_the_product, ux_collective.
2. From each, pick up to 2 articles genuinely about {skill_area}. Skip anything that only mentions it in passing.
3. For each pick, call fetch_article to read the full text.
4. Write 3-5 takeaways per article. Each must be specific enough to act on: a method, a number, a named framework, or a mistake to avoid. No generic advice like "talk to users."
5. Call save_to_notion for each, with 1-3 skill_areas tags.
6. Finish with a short summary: what you saved and any theme that came up across sources."""


if __name__ == "__main__":
    mcp.run()