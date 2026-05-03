# Autonomous Content Aggregator — Project Guidelines

## Project Overview

A command-line tool that fetches the latest news from NYTimes and Ynet via their RSS feeds, summarizes each article using a Claude agent, and saves the results as a chronologically sorted markdown digest.

---

## Architecture

```
candidate34/
├── main.py                  # CLI entry point — orchestrates the full pipeline
├── aggregator/
│   ├── __init__.py
│   ├── fetcher.py           # RSS feed fetching and parsing
│   ├── summarizer.py        # Claude summarization agent
│   ├── formatter.py         # Markdown digest assembly and file output
│   └── retry.py             # Exponential backoff decorator (wraps tenacity)
├── output/                  # Generated markdown digests (gitignored)
├── requirements.txt
└── .env                     # ANTHROPIC_API_KEY (never commit)
```

### Data Flow

```
RSS feeds (feedparser)
    └─> fetcher.py       — returns list of Article objects (title, url, published, summary)
         └─> summarizer.py  — sends each article to Claude, returns enhanced summary
              └─> formatter.py  — sorts by published date (newest first), writes .md file
```

---

## Libraries

| Library | Purpose |
|---|---|
| `feedparser` | Parse RSS/Atom feeds from NYTimes and Ynet; auto-handles `nyt:`, `media:`, `dc:` namespaces |
| `beautifulsoup4` | Strip HTML tags from Ynet RSS `description` field before sending text to Claude |
| `anthropic` | Anthropic Python SDK — Claude API calls |
| `mcp` | MCP Python client — connects to the Brave Search MCP server for summary enrichment |
| `tenacity` | Retry logic with exponential backoff |
| `python-dotenv` | Load API keys from `.env` |
| `rich` | CLI progress output and error display |

Install: `pip install feedparser beautifulsoup4 anthropic mcp tenacity python-dotenv rich`

The Brave Search MCP server runs via `npx` (Node.js required):
```
npx -y @modelcontextprotocol/server-brave-search
```

---

## RSS Feed URLs

| Source | Feed URL |
|---|---|
| NYTimes | `https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml` |
| Ynet | `https://www.ynet.co.il/Integration/StoryRss2.xml` |

---

## Claude Agent (summarizer.py)

- **Model:** `claude-sonnet-4-6`
- **Role:** Secondary summarization agent — receives article title + RSS summary, returns a 2–3 sentence digest in English
- **Prompt structure:** system prompt defines the agent role; user message contains the raw article data
- **Concurrency:** summarize articles sequentially to stay within rate limits
- **Prompt caching:** enable via `cache_control` on the system prompt (static across all calls in a run)

---

## Rate Limit Handling

All Claude API calls must be wrapped with the `retry` decorator from `retry.py`:

- Library: `tenacity`
- Retry on: `anthropic.RateLimitError`, `anthropic.APIStatusError` (5xx)
- Strategy: exponential backoff, base 2s, max delay 60s, max attempts 5
- Log each retry attempt via `rich` to stderr

RSS fetches do not require retry logic — `feedparser` handles HTTP gracefully.

---

## Output Format

- **Filename:** `digest_YYYY-MM-DD_HH-MM.md` saved to `output/`
- **Sort order:** all articles from both sources merged and sorted by `published` date, newest first
- **Structure per article:**

```markdown
## [Article Title](article_url)
**Source:** NYTimes | **Published:** 2026-05-03 14:32

> Claude summary goes here in 2–3 sentences.

---
```

---

## Style Guidelines

- **Python version:** 3.11+
- **No type: ignore** — use proper type hints throughout
- **Dataclass** for `Article` (title, url, source, published: datetime, raw_summary, ai_summary)
- **No global state** — pass dependencies explicitly
- **Environment variables** only via `python-dotenv` — never hardcode keys; required vars: `ANTHROPIC_API_KEY`, `BRAVE_API_KEY`
- **Comments** only where the WHY is non-obvious; no docstrings on simple functions
- **Error handling** at system boundaries only (feed fetch, API call) — let internal errors propagate
- **CLI output** via `rich` — use a progress bar when summarizing articles
