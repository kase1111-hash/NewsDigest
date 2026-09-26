"""Extract command for NewsDigest CLI."""

import sys
from pathlib import Path

import click
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel

from newsdigest.cli.utils import read_source
from newsdigest.config.settings import Config
from newsdigest.core.extractor import Extractor
from newsdigest.exceptions import ExtractionError, IngestError


console = Console()


@click.command()
@click.argument("source")
@click.option(
    "-f",
    "--format",
    "output_format",
    type=click.Choice(["markdown", "json", "text"]),
    default="text",
    help="Output format.",
)
@click.option(
    "-m",
    "--mode",
    type=click.Choice(["conservative", "standard", "aggressive"]),
    default=None,
    help="Extraction mode (how aggressively to compress) (default: configured mode).",
)
@click.option(
    "-o",
    "--output",
    type=click.Path(),
    help="Output file (default: stdout).",
)
@click.option(
    "--stats/--no-stats",
    default=False,
    help="Show extraction statistics.",
)
@click.option(
    "--quiet",
    "-q",
    is_flag=True,
    help="Suppress progress output.",
)
@click.pass_context
def extract(
    ctx: click.Context,
    source: str,
    output_format: str,
    mode: str | None,
    output: str | None,
    stats: bool,
    quiet: bool,
) -> None:
    """Extract signal from a news article.

    SOURCE can be a URL, a path to a text file, raw text, or - for stdin.

    Examples:

        newsdigest extract https://example.com/article

        newsdigest extract article.txt -f json

        newsdigest extract https://example.com/news -m aggressive --stats
    """
    try:
        # File path, "-" for stdin, URL or raw text
        source_content = read_source(source)

        # Initialize extractor
        config = Config.load()
        extractor = Extractor(config=config, mode=mode)

        if not quiet:
            console.print(f"[dim]Extracting from: {escape(source[:80])}...[/dim]")

        # Extract content
        result = extractor.extract_sync(source_content)

        # Format output
        formatted = extractor.format(result, format=output_format)

        # Output stats if requested
        if stats:
            stats_text = extractor.format_stats(result, format="text")
            if not quiet:
                console.print()
                console.print(Panel(stats_text, title="Extraction Statistics"))

        # Write output
        if output:
            Path(output).write_text(formatted, encoding="utf-8")
            if not quiet:
                console.print(f"[green]Output written to: {output}[/green]")
        else:
            click.echo(formatted)

    except IngestError as e:
        console.print(f"[red]Failed to fetch content:[/red] {e}")
        sys.exit(1)
    except ExtractionError as e:
        console.print(f"[red]Extraction failed:[/red] {e}")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)
