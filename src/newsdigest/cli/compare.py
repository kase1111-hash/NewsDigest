"""Compare command for NewsDigest CLI."""

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
    type=click.Choice(["markdown", "text"]),
    default="text",
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
def compare(
    ctx: click.Context,
    source: str,
    output_format: str,
    mode: str | None,
    output: str | None,
    quiet: bool,
) -> None:
    """Show side-by-side comparison of original vs extracted.

    Displays which sentences were kept and which were removed,
    with annotations explaining why content was filtered.

    SOURCE can be a URL, a path to a text file, raw text, or - for stdin.

    Examples:

        newsdigest compare https://example.com/article

        newsdigest compare article.txt -f markdown -o comparison.md
    """
    try:
        # File path, "-" for stdin, URL or raw text
        source_content = read_source(source)

        # Initialize extractor
        config = Config.load()
        extractor = Extractor(config=config, mode=mode)

        if not quiet:
            console.print(f"[dim]Analyzing: {escape(source[:80])}...[/dim]")

        # Extract with comparison data
        result = extractor.compare(source_content)

        if output_format == "markdown":
            formatted = extractor.format_comparison(result, format="markdown")
            if output:
                Path(output).write_text(formatted, encoding="utf-8")
                if not quiet:
                    console.print(f"[green]Output written to: {output}[/green]")
            else:
                click.echo(formatted)
        else:
            # Rich table output
            table = Table(title="Sentence Analysis", show_lines=True)
            table.add_column("#", style="dim", width=4)
            table.add_column("Status", width=10)
            table.add_column("Sentence", width=60)
            table.add_column("Reason", width=20)

            for sentence in result.sentences:
                if sentence.keep:
                    status = "[green]KEEP[/green]"
                else:
                    status = "[red]REMOVE[/red]"
                reason = sentence.removal_reason or "-"
                txt = sentence.text
                text = txt[:100] + "..." if len(txt) > 100 else txt
                table.add_row(str(sentence.index + 1), status, escape(text), reason)

            if output:
                # For file output, use plain text
                lines = []
                for sentence in result.sentences:
                    status = "KEEP" if sentence.keep else "REMOVE"
                    reason = sentence.removal_reason or "-"
                    lines.append(f"{sentence.index + 1}. [{status}] {sentence.text}")
                    if not sentence.keep:
                        lines.append(f"   Reason: {reason}")
                    lines.append("")
                Path(output).write_text("\n".join(lines), encoding="utf-8")
                if not quiet:
                    console.print(f"[green]Output written to: {output}[/green]")
            else:
                console.print(table)

            # Summary
            kept = sum(1 for s in result.sentences if s.keep)
            removed = len(result.sentences) - kept
            console.print()
            console.print(
                f"[bold]Summary:[/bold] {kept} kept, {removed} removed "
                f"({result.statistics.compression_ratio:.0%} compression)"
            )

    except IngestError as e:
        console.print(f"[red]Failed to fetch content:[/red] {e}")
        sys.exit(1)
    except ExtractionError as e:
        console.print(f"[red]Extraction failed:[/red] {e}")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)
