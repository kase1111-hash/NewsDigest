"""Setup command for NewsDigest CLI."""

import subprocess
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel


console = Console()


@click.command("setup")
@click.option(
    "--spacy-model",
    default="en_core_web_sm",
    help="spaCy model to download (default: en_core_web_sm).",
)
@click.option(
    "--skip-spacy",
    is_flag=True,
    help="Skip spaCy model download.",
)
@click.option(
    "--config-dir",
    type=click.Path(),
    default=None,
    help="Directory for configuration files (default: ~/.newsdigest).",
)
@click.option(
    "--force",
    is_flag=True,
    help="Overwrite existing configuration.",
)
@click.pass_context
def setup_cmd(
    ctx: click.Context,
    spacy_model: str,
    skip_spacy: bool,
    config_dir: str | None,
    force: bool,
) -> None:
    """Set up NewsDigest for first use.

    Downloads required models and creates default configuration files.

    Examples:

        newsdigest setup

        newsdigest setup --spacy-model en_core_web_lg

        newsdigest setup --skip-spacy --config-dir ./config
    """
    console.print(Panel("[bold]NewsDigest Setup[/bold]", style="blue"))
    console.print()

    # Determine config directory
    if config_dir:
        config_path = Path(config_dir)
    else:
        config_path = Path.home() / ".newsdigest"

    steps_completed = 0
    steps_total = 3 if not skip_spacy else 2

    # Step 1: Download spaCy model
    if not skip_spacy:
        console.print(f"[1/{steps_total}] Downloading spaCy model: {spacy_model}")
        try:
            result = subprocess.run(
                [sys.executable, "-m", "spacy", "download", spacy_model],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                console.print(f"    [green]Downloaded {spacy_model}[/green]")
                steps_completed += 1
            else:
                console.print(
                    "    [yellow]Warning: Failed to download model[/yellow]"
                )
                console.print(
                    f"    Run manually: python -m spacy download {spacy_model}"
                )
        except Exception as e:
            console.print(f"    [yellow]Warning: {e}[/yellow]")
            console.print(
                f"    Run manually: python -m spacy download {spacy_model}"
            )
    else:
        console.print("[dim]Skipping spaCy model download[/dim]")

    # Step 2: Create config directory
    step_num = 2 if not skip_spacy else 1
    console.print(f"[{step_num}/{steps_total}] Creating configuration directory")
    try:
        config_path.mkdir(parents=True, exist_ok=True)
        console.print(f"    [green]Created: {config_path}[/green]")
        steps_completed += 1
    except Exception as e:
        console.print(f"    [red]Failed: {e}[/red]")

    # Step 3: Create default config file
    step_num = 3 if not skip_spacy else 2
    console.print(f"[{step_num}/{steps_total}] Creating default configuration")

    # The file Config.load() reads by default
    config_file = config_path / "config.yml"
    if config_file.exists() and not force:
        console.print(f"    [yellow]Config exists: {config_file}[/yellow]")
        console.print("    Use --force to overwrite")
    else:
        default_config = """\
# NewsDigest Configuration
# See documentation for all options

# Extraction settings
extraction:
  mode: standard  # conservative, standard, or aggressive
  speculation: remove  # remove, flag, or keep
  emotional_language: remove
  unnamed_sources: flag  # remove, flag, or keep

# Output settings
output:
  show_stats: true
  include_links: true
  show_warnings: true

# Sources for digest generation
# sources:
#   - type: rss
#     url: https://feeds.example.com/rss
#     name: Example Feed
#     category: tech

# Digest settings
digest:
  similarity_threshold: 0.7
  min_novelty_score: 0.3
  period: 24h
"""
        try:
            config_file.write_text(default_config, encoding="utf-8")
            console.print(f"    [green]Created: {config_file}[/green]")
            steps_completed += 1
        except Exception as e:
            console.print(f"    [red]Failed: {e}[/red]")

    # Summary
    console.print()
    if steps_completed == steps_total:
        console.print("[green]Setup complete![/green]")
        console.print()
        console.print("Get started:")
        console.print("  newsdigest extract <url>     # Extract from a URL")
        console.print("  newsdigest compare <url>     # See what was removed")
        console.print("  newsdigest --help            # Show all commands")
    else:
        msg = f"Setup partially complete ({steps_completed}/{steps_total} steps)"
        console.print(f"[yellow]{msg}[/yellow]")
        console.print(
            "Review warnings above and complete setup manually if needed."
        )
