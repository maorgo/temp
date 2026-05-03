import json
import subprocess

from aggregator.models import Article, SynthesizedContent

_MODEL = "claude-sonnet-4-6"

_SYSTEM_PROMPT = """You are a news research agent. Your task is to find 2-3 additional facts or context about a news topic that are NOT already covered in the provided summary points.

Use the search tool to look up the topic, then respond with exactly this format:

EXTRA FACTS:
- <additional fact 1>
- <additional fact 2>
- <additional fact 3 if warranted>

Rules:
- Be strictly factual and objective.
- Do not repeat information already in the existing bullets.
- Respond in the same language as the article title.
- Provide 2 to 3 facts maximum."""


def enrich(article: Article, synthesis: SynthesizedContent) -> list[str]:
    try:
        return _enrich(article, synthesis)
    except Exception as exc:
        from rich.console import Console
        Console(stderr=True).print(f"[yellow]Enrichment skipped: {exc}[/yellow]")
        return []


def _enrich(article: Article, synthesis: SynthesizedContent) -> list[str]:
    mcp_config = json.dumps({
        "mcpServers": {
            "duckduckgo": {
                "command": "npx",
                "args": ["-y", "duckduckgo-mcp-server"],
            }
        }
    })

    existing = "\n".join(f"- {b}" for b in synthesis.bullets)
    user_message = (
        f"Article title: {article.title}\n\n"
        f"Existing summary points (do NOT repeat these):\n{existing}\n\n"
        f"Search for 2-3 additional facts or recent context about this topic."
    )

    result = subprocess.run(
        [
            "claude", "-p", user_message,
            "--model", _MODEL,
            "--system-prompt", _SYSTEM_PROMPT,
            "--mcp-config", mcp_config,
            "--tools", "",
            "--allowedTools", "mcp__duckduckgo__search",
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    return _parse_extra_facts(result.stdout)


def _parse_extra_facts(text: str) -> list[str]:
    facts = []
    in_section = False
    for line in text.splitlines():
        line = line.strip()
        if "EXTRA FACTS" in line.upper():
            in_section = True
            continue
        if in_section and line.startswith("-"):
            facts.append(line.removeprefix("-").strip())
    return facts[:3]
