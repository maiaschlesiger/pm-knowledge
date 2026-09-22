# pm-knowledge

An MCP server that builds a structured Notion knowledge base of product management and product design articles. Claude fetches articles from curated sources, extracts concrete takeaways, and saves them as rows in a Notion database.

**Domain:** Knowledge Management

## Components

| Type | Name | What it does |
|---|---|---|
| Tool | `fetch_feed` | Lists recent articles from an allowlisted RSS source |
| Tool | `fetch_article` | Fetches an article's readable text (SSRF-protected) |
| Tool | `save_to_notion` | Saves an article with tags and takeaways to Notion (rate-limited) |
| Prompt | `skill_digest` | Guides Claude to build a digest on one skill, e.g. "user research" |

The server fetches and stores; Claude does the summarizing. No LLM is called from inside the server.

## Setup

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

1. Clone the repo and install dependencies:
```bash
   git clone https://github.com/maiaschlesiger/pm-knowledge.git
   cd pm-knowledge
   uv sync
```
   (Or with pip: `python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`)

2. Create a Notion integration at https://www.notion.so/my-integrations and copy its token.

3. Create a Notion database with these columns:

   | Column | Type |
   |---|---|
   | Name | Title |
   | URL | URL |
   | Source | Text |
   | Skill Area | Multi-select |
   | Takeaways | Text |
   | Status | Select |

   Share the database with your integration: database menu (•••) → Connections → add the integration.

4. Copy `.env.example` to `.env` and fill in your token and database ID:
```bash
   cp .env.example .env
```
   Secrets are loaded from `.env` via `pathlib`, never from system environment variables. `.env` is gitignored.

5. Check the Notion connection: `uv run test_notion.py` should add a "Test entry" row.

## Running

- **MCP Inspector (for testing):** `uv run mcp dev server.py`
- **Claude Desktop:** copy the entry from `claude_desktop_config.json` into your Claude Desktop config (Settings → Developer → Edit Config), replacing both absolute paths with your own (`which uv` for the uv path). Fully quit and reopen Claude Desktop.

Try: *"Use the skill_digest prompt for user research."*

## Security best practices

**1. Input sanitization (SSRF protection).** `fetch_article` accepts a URL, so without checks Claude could be steered into fetching internal addresses such as the cloud metadata endpoint (`169.254.169.254`), local services, or `file://` paths. `is_safe_url` enforces three checks: http/https only, hostname on a domain allowlist (exact or subdomain match), and hostname must not resolve to a private, loopback, or link-local IP. Redirects are not followed, so an allowed site cannot bounce the request to an internal address.

**2. Rate limiting.** A sliding-window limiter caps `save_to_notion` at 10 calls per minute and `fetch_article` at 30 per minute. This keeps a runaway agent loop from flooding the Notion database, respects Notion's API limits, and avoids hammering source sites. Over-limit calls return an error instead of waiting.

**Exploit demo:** `uv run demo_exploits.py` runs each attack against the real tool functions and shows it blocked. The Notion API call is stubbed in the rate-limit demo so it doesn't create real rows.

## Notes

- `mcp` is pinned below 2.0 because v2 renamed `FastMCP` and most reference material targets v1.
- The rate limiter is in memory, so it resets when the server restarts.

## Code citations

- Server setup follows the FastMCP quickstart in the MCP Python SDK README: https://github.com/modelcontextprotocol/python-sdk (cited in `server.py`).
- SSRF defense (scheme check, domain allowlist, private/loopback/link-local IP filtering) follows standard SSRF-prevention patterns, not copied from a specific source.
- Code written with the help of Claude (Anthropic) as an AI coding assistant.
