"""Analytics command for NewsDigest CLI."""

import sys
from pathlib import Path

import click
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table

from newsdigest.cli.utils import read_source
from newsdigest.config.settings import Config
from newsdigest.core.extractor import Extractor
from newsdigest.exceptions import ExtractionError, IngestError


console = Console()


@click.command()
@click.argument("sources", nargs=-1)
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
def analytics(
    ctx: click.Context,
    sources: tuple[str, ...],
    output_format: str,
    output: str | None,
    quiet: bool,
) -> None:
    """Analyze multiple articles and show aggregate statistics.

    Provides insights across multiple sources including average
    compression ratios, common removal reasons, and source quality metrics.

    SOURCES can be URLs, paths to text files, or raw text.

    Examples:

        newsdigest analytics https://example.com/article1 https://example.com/article2

        newsdigest analytics *.txt -f json
    """
    if not sources:
        console.print("[yellow]No sources specified.[/yellow]")
        console.print("Provide URLs or file paths as arguments.")
        sys.exit(1)

    try:
        # Initialize extractor
        config = Config.load()
        extractor = Extractor(config=config)

        results = []
        failed = []

        for source in sources:
            try:
                # File path, "-" for stdin, URL or raw text
                source_content = read_source(source)

                if not quiet:
                    console.print(f"[dim]Analyzing: {escape(source[:60])}...[/dim]")

                result = extractor.extract_sync(source_content)
                results.append({"source": source, "result": result})

            except (IngestError, ExtractionError) as e:
                failed.append({"source": source, "error": str(e)})
                if not quiet:
                    console.print(
                        f"[yellow]Skipped: {escape(source[:40])}... ({escape(str(e))})[/yellow]"
                    )

        if not results:
            console.print("[red]No articles could be analyzed.[/red]")
            sys.exit(1)

        # Calculate aggregate statistics
        total_original = sum(r["result"].statistics.original_words for r in results)
        total_compressed = sum(r["result"].statistics.compressed_words for r in results)
        avg_compression = (
            1 - total_compressed / total_original if total_original > 0 else 0
        )
        total_claims = sum(len(r["result"].claims) for r in results)
        total_speculation = sum(
            r["result"].statistics.speculation_removed for r in results
        )
        total_emotional = sum(
            r["result"].statistics.emotional_words_removed for r in results
        )
        total_unnamed = sum(r["result"].statistics.unnamed_sources for r in results)
        total_named = sum(r["result"].statistics.named_sources for r in results)

        # Per-article stats
        compressions = [r["result"].statistics.compression_ratio for r in results]
        avg_article_compression = sum(compressions) / len(compressions)
        min_compression = min(compressions)
        max_compression = max(compressions)

        if output_format == "json":
            import json

            analytics_dict = {
                "articles_analyzed": len(results),
                "articles_failed": len(failed),
                "totals": {
                    "original_words": total_original,
                    "compressed_words": total_compressed,
                    "claims_extracted": total_claims,
                    "speculation_removed": total_speculation,
                    "emotional_words_removed": total_emotional,
                    "named_sources": total_named,
                    "unnamed_sources": total_unnamed,
                },
                "averages": {
                    "compression_ratio": round(avg_compression, 3),
                    "compression_per_article": round(avg_article_compression, 3),
                },
                "ranges": {
                    "min_compression": round(min_compression, 3),
                    "max_compression": round(max_compression, 3),
                },
                "per_article": [
                    {
                        "source": r["source"][:50],
                        "original_words": r["result"].statistics.original_words,
                        "compressed_words": r["result"].statistics.compressed_words,
                        "compression_ratio": r["result"].statistics.compression_ratio,
                        "claims": len(r["result"].claims),
                    }
                    for r in results
                ],
            }
            formatted = json.dumps(analytics_dict, indent=2)

            if output:
                Path(output).write_text(formatted, encoding="utf-8")
                if not quiet:
                    console.print(f"[green]Output written to: {output}[/green]")
            else:
                click.echo(formatted)

        elif output_format == "text":
            lines = [
                f"Articles analyzed: {len(results)}",
                f"Articles failed: {len(failed)}",
                "",
                "Totals:",
                f"  Original words: {total_original:,}",
                f"  Compressed words: {total_compressed:,}",
                f"  Claims extracted: {total_claims}",
                f"  Speculation removed: {total_speculation}",
                f"  Emotional words removed: {total_emotional}",
                "",
                "Averages:",
                f"  Overall compression: {avg_compression:.1%}",
                f"  Per-article compression: {avg_article_compression:.1%}",
                f"  Range: {min_compression:.1%} - {max_compression:.1%}",
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
            console.print()

            # Summary panel
            summary = (
                f"Analyzed [bold]{len(results)}[/bold] article(s), "
                f"[yellow]{len(failed)}[/yellow] failed\n\n"
                f"Total words: [bold]{total_original:,}[/bold] -> "
                f"[green]{total_compressed:,}[/green] "
                f"([green]{avg_compression:.1%}[/green] compression)\n"
                f"Claims extracted: [bold]{total_claims}[/bold]\n"
                f"Speculation removed: {total_speculation} sentences\n"
                f"Emotional words removed: {total_emotional}\n"
                f"Sources: {total_named} named, {total_unnamed} unnamed"
            )
            console.print(Panel(summary, title="Analytics Summary"))

            console.print()

            # Per-article table
            table = Table(title="Per-Article Breakdown")
            table.add_column("Source", width=40)
            table.add_column("Original", justify="right")
            table.add_column("Compressed", justify="right")
            table.add_column("Ratio", justify="right")
            table.add_column("Claims", justify="right")

            for r in results:
                src = r["source"]
                source_short = src[:37] + "..." if len(src) > 40 else src
                stats = r["result"].statistics
                table.add_row(
                    escape(source_short),
                    str(stats.original_words),
                    str(stats.compressed_words),
                    f"{stats.compression_ratio:.1%}",
                    str(len(r["result"].claims)),
                )

            console.print(table)

            if failed:
                console.print()
                console.print("[yellow]Failed sources:[/yellow]")
                for f in failed:
                    console.print(f"  - {escape(f['source'][:50])}...")

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)
