"""Sources command for NewsDigest CLI."""

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
def sources(
    ctx: click.Context,
    source: str,
    output_format: str,
    output: str | None,
    quiet: bool,
) -> None:
    """Analyze source attribution in an article.

    Shows named sources, unnamed/anonymous sources, and flags
    potential attribution issues.

    SOURCE can be a URL, a path to a text file, raw text, or - for stdin.

    Examples:

        newsdigest sources https://example.com/article

        newsdigest sources article.txt -f json
    """
    try:
        # File path, "-" for stdin, URL or raw text
        source_content = read_source(source)

        # Initialize extractor
        config = Config.load()
        extractor = Extractor(config=config)

        if not quiet:
            console.print(f"[dim]Analyzing sources in: {escape(source[:80])}...[/dim]")

        # Extract content
        result = extractor.extract_sync(source_content)

        # Gather source information
        named_sources = result.sources_named
        unnamed_count = result.statistics.unnamed_sources

        # Find sentences with unnamed sources
        unnamed_sentences = [s for s in result.sentences if s.has_unnamed_source]

        if output_format == "json":
            import json

            sources_dict = {
                "named_sources": named_sources,
                "unnamed_source_count": unnamed_count,
                "unnamed_source_sentences": [
                    {"index": s.index, "text": s.text} for s in unnamed_sentences
                ],
                "warnings": result.warnings,
            }
            formatted = json.dumps(sources_dict, indent=2)

            if output:
                Path(output).write_text(formatted, encoding="utf-8")
                if not quiet:
                    console.print(f"[green]Output written to: {output}[/green]")
            else:
                click.echo(formatted)

        elif output_format == "text":
            lines = ["Named Sources:", "-" * 40]
            if named_sources:
                lines.extend(f"  - {src}" for src in named_sources)
            else:
                lines.append("  (none found)")

            lines.extend(["", "Unnamed Source References:", "-" * 40])
            if unnamed_sentences:
                lines.extend(
                    f"  [{s.index + 1}] {s.text[:100]}..." for s in unnamed_sentences
                )
            else:
                lines.append("  (none found)")

            formatted = "\n".join(lines)

            if output:
                Path(output).write_text(formatted, encoding="utf-8")
                if not quiet:
                    console.print(f"[green]Output written to: {output}[/green]")
            else:
                click.echo(formatted)

        else:
            # Rich table output
            console.print()

            # Named sources table
            if named_sources:
                table = Table(title="Named Sources")
                table.add_column("#", style="dim", width=4)
                table.add_column("Source Name")

                for i, src in enumerate(named_sources, 1):
                    table.add_row(str(i), escape(src))

                console.print(table)
            else:
                console.print("[yellow]No named sources found.[/yellow]")

            console.print()

            # Unnamed sources
            if unnamed_sentences:
                table = Table(title="Unnamed Source References")
                table.add_column("Sentence", style="dim", width=4)
                table.add_column("Text", width=70)

                for s in unnamed_sentences:
                    text = s.text[:100] + "..." if len(s.text) > 100 else s.text
                    table.add_row(str(s.index + 1), escape(text))

                console.print(table)
            else:
                console.print("[green]No unnamed sources found.[/green]")

            # Summary
            console.print()
            console.print(
                f"[bold]Summary:[/bold] {len(named_sources)} named, "
                f"{unnamed_count} unnamed source references"
            )

            # Warnings
            if result.warnings:
                console.print()
                console.print("[yellow]Warnings:[/yellow]")
                for warning in result.warnings:
                    warn_type = warning.get("type")
                    warn_text = warning.get("text", "")[:50]
                    console.print(f"  - {warn_type}: {escape(warn_text)}...")

    except IngestError as e:
        console.print(f"[red]Failed to fetch content:[/red] {e}")
        sys.exit(1)
    except ExtractionError as e:
        console.print(f"[red]Extraction failed:[/red] {e}")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)
