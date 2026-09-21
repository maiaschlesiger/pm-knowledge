# Server setup adapted from the FastMCP quickstart in the MCP Python SDK README:
# https://github.com/modelcontextprotocol/python-sdk
import logging
import sys
from pathlib import Path

import feedparser
import httpx
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


if __name__ == "__main__":
    mcp.run()