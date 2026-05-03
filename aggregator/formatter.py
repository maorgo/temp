from datetime import datetime
from pathlib import Path

from aggregator.models import Article, SynthesizedContent


def write_digest(results: list[tuple[Article, SynthesizedContent]]) -> Path:
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    path = Path("output") / f"digest_{timestamp}.md"
    path.parent.mkdir(exist_ok=True)

    header = f"# News Digest — {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
    blocks = [header]

    for article, synthesis in results:
        published = article.published.strftime("%Y-%m-%d %H:%M")
        block = [
            f"## [{synthesis.title}]({article.url})",
            f"**Source:** {article.source} | **Published:** {published}\n",
        ]

        for bullet in synthesis.bullets:
            block.append(f"- {bullet}")

        if synthesis.extra_bullets:
            block.append("\n**Additional context:**")
            for bullet in synthesis.extra_bullets:
                block.append(f"- {bullet}")

        block.append(f"\n> {synthesis.conclusion}")
        block.append("\n---\n")
        blocks.append("\n".join(block))

    path.write_text("\n".join(blocks), encoding="utf-8")
    return path
