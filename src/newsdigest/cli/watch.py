"""Watch command for NewsDigest CLI."""

import asyncio
import sys
import time
from datetime import datetime

import click
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel

from newsdigest.config.settings import Config
from newsdigest.digest.generator import DigestGenerator


console = Console()


@click.command()
@click.option(
    "-s",
    "--source",
    "sources",
    multiple=True,
    required=True,
    help="RSS feed URL to watch (can be specified multiple times).",
)
@click.option(
    "-i",
    "--interval",
    default=300,
    type=int,
    help="Check interval in seconds (default: 300).",
)
@click.option(
    "-f",
    "--format",
    "output_format",
    type=click.Choice(["summary", "full", "json"]),
    default="summary",
    help="Output format for new articles.",
)
@click.option(
    "--once",
    is_flag=True,
    help="Check once and exit (don't watch continuously).",
)
@click.pass_context
def watch(
    ctx: click.Context,
    sources: tuple[str, ...],
    interval: int,
    output_format: str,
    once: bool,
) -> None:
    """Watch RSS feeds for new articles.

    Continuously monitors feeds and extracts new articles as they appear.

    Examples:

        newsdigest watch -s https://feeds.example.com/rss

        newsdigest watch -s https://feed1.com/rss -s https://feed2.com/rss -i 600

        newsdigest watch -s https://feeds.example.com/rss --once
    """
    try:
        # Initialize generator
        config = Config.load()
        generator = DigestGenerator(config=config)

        # Add sources
        for source_url in sources:
            generator.add_rss(source_url)

        console.print(f"[bold]Watching {len(sources)} feed(s)[/bold]")
        console.print(f"Check interval: {interval} seconds")
        console.print()

        # Track seen article IDs
        seen_ids: set[str] = set()
        last_check = datetime.utcnow()

        async def check_feeds() -> list:
            """Check feeds for new articles."""
            nonlocal last_check
            try:
                result = await generator.generate_async(period="1h", format="dict")
                new_articles = []

                for topic in result.topics:
                    for item in topic.items:
                        if item.id not in seen_ids:
                            seen_ids.add(item.id)
                            new_articles.append(item)

                last_check = datetime.utcnow()
                return new_articles
            except Exception as e:
                console.print(f"[yellow]Check failed: {e}[/yellow]")
                return []

        def display_article(item) -> None:
            """Display a new article."""
            if output_format == "json":
                import json

                article_dict = {
                    "id": item.id,
                    "summary": item.summary,
                    "sources": item.sources,
                    "urls": item.urls,
                    "topic": item.topic,
                    "original_words": item.original_words,
                    "compressed_words": item.compressed_words,
                }
                click.echo(json.dumps(article_dict, indent=2))
            elif output_format == "full":
                console.print(
                    Panel(
                        escape(item.summary),
                        title=f"[bold]{escape(item.topic or 'News')}[/bold]",
                        subtitle=escape(f"Sources: {', '.join(item.sources)}"),
                    )
                )
            else:
                # Summary format
                compression = (
                    f"{(1 - item.compressed_words / item.original_words) * 100:.0f}%"
                    if item.original_words > 0
                    else "N/A"
                )
                topic = escape(f"[{item.topic or 'News'}]")
                console.print(
                    f"[green]+[/green] {topic} "
                    f"{escape(item.summary[:100])}... ({compression} compressed)"
                )

        if once:
            # Single check
            new_articles = asyncio.run(check_feeds())
            if new_articles:
                console.print(f"[bold]Found {len(new_articles)} article(s)[/bold]")
                console.print()
                for item in new_articles:
                    display_article(item)
            else:
                console.print("[dim]No new articles found.[/dim]")
        else:
            # Continuous watch
            console.print("[dim]Press Ctrl+C to stop watching.[/dim]")
            console.print()

            try:
                while True:
                    new_articles = asyncio.run(check_feeds())

                    if new_articles:
                        console.print(
                            f"[bold][{datetime.now().strftime('%H:%M:%S')}] "
                            f"Found {len(new_articles)} new article(s)[/bold]"
                        )
                        for item in new_articles:
                            display_article(item)
                        console.print()
                    else:
                        console.print(
                            f"[dim][{datetime.now().strftime('%H:%M:%S')}] "
                            f"No new articles[/dim]"
                        )

                    # Wait for next check
                    time.sleep(interval)

            except KeyboardInterrupt:
                console.print()
                console.print("[yellow]Watch stopped.[/yellow]")
                console.print(f"Processed {len(seen_ids)} unique article(s) total.")

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)
