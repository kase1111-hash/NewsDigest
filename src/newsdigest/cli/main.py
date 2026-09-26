"""Main CLI application for NewsDigest."""

import click

from newsdigest.version import __version__


@click.group()
@click.version_option(version=__version__, prog_name="newsdigest")
@click.pass_context
def cli(ctx: click.Context) -> None:
    """NewsDigest - Semantic compression engine for news.

    Extract signal from noise. Your 4-hour news habit, compressed to 5 minutes.
    """
    ctx.ensure_object(dict)


# Import and register commands
# These imports must come after the cli group is defined
from newsdigest.cli.analytics import analytics  # noqa: E402
from newsdigest.cli.compare import compare  # noqa: E402
from newsdigest.cli.digest import digest  # noqa: E402
from newsdigest.cli.extract import extract  # noqa: E402
from newsdigest.cli.setup import setup_cmd  # noqa: E402
from newsdigest.cli.sources import sources  # noqa: E402
from newsdigest.cli.stats import stats  # noqa: E402
from newsdigest.cli.watch import watch  # noqa: E402


cli.add_command(extract)
cli.add_command(compare)
cli.add_command(stats)
cli.add_command(digest)
cli.add_command(sources)
cli.add_command(watch)
cli.add_command(analytics)
cli.add_command(setup_cmd, name="setup")


if __name__ == "__main__":
    cli()
