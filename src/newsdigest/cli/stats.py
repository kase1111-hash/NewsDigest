"""Stats command for NewsDigest CLI."""

import sys
from pathlib import Path

import click
from rich.console import Console
from rich.markup import escape
from rich.table import Table

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
    type=click.Choice(["table", "json", "text"]),
    default="table",
    help="Output format.",
)
@click.option(
    "-m",
    "--mode",
    type=click.Choice(["conservative", "standard", "aggressive"]),
    default=None,
    help="Extraction mode (default: configured mode).",
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
def stats(
    ctx: click.Context,
    source: str,
    output_format: str,
    mode: str | None,
    output: str | None,
    quiet: bool,
) -> None:
    """Show extraction statistics for an article.

    Displays detailed statistics about what was removed and why,
    compression ratios, and content density metrics.

    SOURCE can be a URL, a path to a text file, raw text, or - for stdin.

    Examples:

        newsdigest stats https://example.com/article

        newsdigest stats article.txt -f json
    """
    try:
        # File path, "-" for stdin, URL or raw text
        source_content = read_source(source)

        # Initialize extractor
        config = Config.load()
        extractor = Extractor(config=config, mode=mode)

        if not quiet:
            console.print(f"[dim]Analyzing: {escape(source[:80])}...[/dim]")

        # Extract content
        result = extractor.extract_sync(source_content)
        s = result.statistics

        if output_format == "json":
            import json

            stats_dict = {
                "original_words": s.original_words,
                "compressed_words": s.compressed_words,
                "compression_ratio": s.compression_ratio,
                "original_density": s.original_density,
                "compressed_density": s.compressed_density,
                "novel_claims": s.novel_claims,
                "background_removed": s.background_removed,
                "speculation_removed": s.speculation_removed,
                "repetition_collapsed": s.repetition_collapsed,
                "emotional_words_removed": s.emotional_words_removed,
                "named_sources": s.named_sources,
                "unnamed_sources": s.unnamed_sources,
            }
            formatted = json.dumps(stats_dict, indent=2)

            if output:
                Path(output).write_text(formatted, encoding="utf-8")
                if not quiet:
                    console.print(f"[green]Output written to: {output}[/green]")
            else:
                click.echo(formatted)

        elif output_format == "text":
            lines = [
                f"Original words: {s.original_words}",
                f"Compressed words: {s.compressed_words}",
                f"Compression ratio: {s.compression_ratio:.1%}",
                f"Original density: {s.original_density:.2f}",
                f"Compressed density: {s.compressed_density:.2f}",
                f"Novel claims: {s.novel_claims}",
                f"Background removed: {s.background_removed}",
                f"Speculation removed: {s.speculation_removed}",
                f"Repetition collapsed: {s.repetition_collapsed}",
                f"Emotional words removed: {s.emotional_words_removed}",
                f"Named sources: {s.named_sources}",
                f"Unnamed sources: {s.unnamed_sources}",
            ]
            formatted = "\n".join(lines)

            if output:
                Path(output).write_text(formatted, encoding="utf-8")
                if not quiet:
                    console.print(f"[green]Output written to: {output}[/green]")
            else:
                click.echo(formatted)

        else:
            # Rich table output
            table = Table(title="Extraction Statistics")
            table.add_column("Metric", style="bold")
            table.add_column("Value", justify="right")

            table.add_row("Original words", str(s.original_words))
            table.add_row("Compressed words", str(s.compressed_words))
            table.add_row("Compression ratio", f"{s.compression_ratio:.1%}")
            table.add_row("", "")
            table.add_row("Original density", f"{s.original_density:.2f}")
            table.add_row("Compressed density", f"{s.compressed_density:.2f}")
            table.add_row("", "")
            table.add_row("Novel claims", str(s.novel_claims))
            table.add_row("Background removed", str(s.background_removed))
            table.add_row("Speculation removed", str(s.speculation_removed))
            table.add_row("Repetition collapsed", str(s.repetition_collapsed))
            table.add_row("Emotional words removed", str(s.emotional_words_removed))
            table.add_row("", "")
            table.add_row("Named sources", str(s.named_sources))
            table.add_row("Unnamed sources", str(s.unnamed_sources))

            if output:
                # Plain text for file
                lines = [
                    f"Original words: {s.original_words}",
                    f"Compressed words: {s.compressed_words}",
                    f"Compression ratio: {s.compression_ratio:.1%}",
                ]
                Path(output).write_text("\n".join(lines), encoding="utf-8")
                if not quiet:
                    console.print(f"[green]Output written to: {output}[/green]")
            else:
                console.print(table)

    except IngestError as e:
        console.print(f"[red]Failed to fetch content:[/red] {e}")
        sys.exit(1)
    except ExtractionError as e:
        console.print(f"[red]Extraction failed:[/red] {e}")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)
