import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn

from aggregator import ynet_scraper
from aggregator.formatter import write_digest
from aggregator.models import Article, SynthesizedContent
from Agents.summarizer_agent import call_claude
from Agents.enricher_agent import enrich

MAX_WORKERS = 5
console = Console(stderr=True)


def _summarize(article: Article) -> tuple[Article, SynthesizedContent]:
    t0 = time.time()
    result = call_claude(article)
    elapsed = time.time() - t0
    console.print(f"  [green]✓[/green] Summarized [{elapsed:.1f}s]: {article.title[:70]}")
    return article, result


def _enrich_one(article: Article, synthesis: SynthesizedContent) -> tuple[Article, SynthesizedContent]:
    t0 = time.time()
    synthesis.extra_bullets = enrich(article, synthesis)
    elapsed = time.time() - t0
    facts = len(synthesis.extra_bullets)
    console.print(f"  [cyan]✓[/cyan] Enriched  [{elapsed:.1f}s] ({facts} facts): {article.title[:65]}")
    return article, synthesis


def main() -> None:
    total_start = time.time()
    progress_cols = [SpinnerColumn(), BarColumn(), TextColumn("{task.completed}/{task.total}"), TimeElapsedColumn()]

    console.print("\n[bold]── Phase 0: Fetching articles ──[/bold]")
    articles: list[Article] = []
    try:
        articles.extend(ynet_scraper.fetch())
        console.print(f"  Fetched [bold]{len(articles)}[/bold] articles from Ynet")
    except Exception as exc:
        console.print(f"  [red]Ynet fetch failed — {exc}[/red]")

    if not articles:
        console.print("[red]Error: no articles fetched.[/red]")
        sys.exit(1)

    # Phase 1: summarize all articles concurrently
    console.print(f"\n[bold]── Phase 1: Summarizing ({MAX_WORKERS} workers) ──[/bold]")
    syntheses: list[tuple[Article, SynthesizedContent]] = []
    phase1_start = time.time()
    with Progress(*progress_cols, console=Console(stderr=True)) as progress:
        task = progress.add_task("", total=len(articles))
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {executor.submit(_summarize, a): a for a in articles}
            for future in as_completed(futures):
                progress.advance(task)
                try:
                    syntheses.append(future.result())
                except Exception as exc:
                    article = futures[future]
                    console.print(f"  [red]✗ Failed: {article.title[:70]} — {exc}[/red]")

    console.print(f"  Phase 1 done: {len(syntheses)}/{len(articles)} succeeded in {time.time()-phase1_start:.1f}s")

    if not syntheses:
        console.print("[red]Error: all articles failed to summarize.[/red]")
        sys.exit(1)

    # Phase 2: enrich all summaries concurrently
    console.print(f"\n[bold]── Phase 2: Enriching ({MAX_WORKERS} workers) ──[/bold]")
    results: list[tuple[Article, SynthesizedContent]] = []
    phase2_start = time.time()
    with Progress(*progress_cols, console=Console(stderr=True)) as progress:
        task = progress.add_task("", total=len(syntheses))
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {
                executor.submit(_enrich_one, article, synthesis): article
                for article, synthesis in syntheses
            }
            for future in as_completed(futures):
                progress.advance(task)
                try:
                    results.append(future.result())
                except Exception as exc:
                    article = futures[future]
                    console.print(f"  [red]✗ Failed: {article.title[:70]} — {exc}[/red]")

    console.print(f"  Phase 2 done: {len(results)}/{len(syntheses)} succeeded in {time.time()-phase2_start:.1f}s")

    results.sort(key=lambda pair: pair[0].published, reverse=True)

    console.print(f"\n[bold]── Writing digest ──[/bold]")
    path = write_digest(results)
    console.print(f"  [bold green]Done![/bold green] Digest written to: {path}")
    console.print(f"  Total time: {time.time()-total_start:.1f}s\n")
    print(path)


if __name__ == "__main__":
    main()
