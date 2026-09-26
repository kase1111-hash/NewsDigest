"""Digest command for NewsDigest CLI."""

import sys
from pathlib import Path

import click
from rich.console import Console

from newsdigest.config.settings import Config
from newsdigest.digest.generator import DigestGenerator
from newsdigest.exceptions import DigestError


console = Console()


@click.command()
@click.option(
    "-s",
    "--source",
    "sources",
    multiple=True,
    help="RSS feed URL to include (can be specified multiple times).",
)
@click.option(
    "-c",
    "--config",
    "config_file",
    type=click.Path(exists=True),
    help="Path to sources config file (YAML).",
)
@click.option(
    "-p",
    "--period",
    default="24h",
    help="Time period for digest (e.g., 24h, 7d, 1w).",
)
@click.option(
    "-f",
    "--format",
    "output_format",
    type=click.Choice(["markdown", "json", "text"]),
    default="markdown",
    help="Output format.",
)
@click.option(
    "-o",
    "--output",
    type=click.Path(),
    help="Output file (default: stdout).",
)
@click.option(
    "--quiet",
    "-q",
    is_flag=True,
    help="Suppress progress output.",
)
@click.pass_context
def digest(
    ctx: click.Context,
    sources: tuple[str, ...],
    config_file: str | None,
    period: str,
    output_format: str,
    output: str | None,
    quiet: bool,
) -> None:
    """Generate a digest from multiple news sources.

    Fetches articles from RSS feeds, extracts content, deduplicates,
    clusters by topic, and produces a compressed digest.

    Examples:

        newsdigest digest -s https://feeds.example.com/rss

        newsdigest digest -s https://feed1.com/rss -s https://feed2.com/rss -p 48h

        newsdigest digest -c sources.yaml -f json -o digest.json
    """
    try:
        # Initialize generator
        config = Config.load()
        generator = DigestGenerator(config=config)

        # Load sources from config file if provided
        if config_file:
            import yaml

            with Path(config_file).open(encoding="utf-8") as f:
                sources_config = yaml.safe_load(f) or {}

            for source in sources_config.get("sources", []):
                if source.get("type") == "rss":
                    generator.add_rss(
                        url=source["url"],
                        name=source.get("name"),
                        category=source.get("category"),
                    )
                elif source.get("type") == "url":
                    generator.add_url(
                        url=source["url"],
                        name=source.get("name"),
                    )

        # Add CLI-specified sources
        for source_url in sources:
            generator.add_rss(source_url)

        # Check we have sources
        if not generator.get_sources():
            console.print("[yellow]No sources specified.[/yellow]")
            console.print(
                "Use -s/--source to add RSS feeds or -c/--config for a config file."
            )
            sys.exit(1)

        if not quiet:
            source_count = len(generator.get_sources())
            msg = f"Generating {period} digest from {source_count} source(s)..."
            console.print(f"[dim]{msg}[/dim]")

        # Generate digest
        result = generator.generate(period=period, format=output_format)

        # Write output
        if output:
            Path(output).write_text(str(result), encoding="utf-8")
            if not quiet:
                console.print(f"[green]Digest written to: {output}[/green]")
        else:
            click.echo(result)

    except DigestError as e:
        console.print(f"[red]Digest generation failed:[/red] {e}")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)
