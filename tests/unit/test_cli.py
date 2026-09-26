"""Tests for CLI output handling."""

import json

import pytest
from click.testing import CliRunner

from newsdigest.cli.main import cli


LONG_ARTICLE = (
    "Apple reported quarterly revenue of $89.5 billion on Tuesday, beating analyst "
    "expectations of $87.1 billion, while services revenue rose to a record high. "
    "CEO Tim Cook said iPhone sales in emerging markets exceeded the company's own "
    "internal forecasts by a wide margin during the quarter."
)


@pytest.fixture
def runner(monkeypatch, tmp_path) -> CliRunner:
    """CLI runner isolated from the user's config and environment."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("NEWSDIGEST_CONFIG", raising=False)
    monkeypatch.delenv("NEWSDIGEST_MODE", raising=False)
    return CliRunner()


class TestCLIOutput:
    """Tests for machine-readable and markup-safe output."""

    @pytest.mark.parametrize("command", [
        ["extract", "-q", "-f", "json"],
        ["stats", "-q", "-f", "json"],
    ])
    def test_json_output_is_valid(self, runner, command):
        """Test JSON output isn't hard-wrapped by the terminal renderer."""
        result = runner.invoke(cli, [*command, LONG_ARTICLE])

        assert result.exit_code == 0, result.output
        json.loads(result.output)

    def test_extract_json_content(self, runner):
        """Test the extracted text is carried through intact."""
        result = runner.invoke(cli, ["extract", "-q", "-f", "json", LONG_ARTICLE])
        data = json.loads(result.output)
        assert "$89.5 billion" in data["extracted"]["text"]

    @pytest.mark.parametrize("command", [
        ["extract", "-q"],
        ["compare", "-q"],
        ["sources", "-q"],
    ])
    def test_markup_like_text_is_printed_literally(self, runner, command):
        """Test "[/quote]"-style text neither crashes nor gets swallowed."""
        text = "Officials said the [bold] plan [/quote] costs $5 billion in total."
        result = runner.invoke(cli, [*command, text])

        assert result.exit_code == 0, result.output
        if command[0] != "sources":
            assert "[/quote]" in result.output

    def test_mode_defaults_to_config_file(self, runner, tmp_path):
        """Test extract uses the configured mode unless -m is given."""
        config_dir = tmp_path / ".newsdigest"
        config_dir.mkdir()
        (config_dir / "config.yml").write_text("extraction:\n  mode: aggressive\n")
        text = "The dangerous storm hit the Florida coast on Monday, officials said."

        configured = runner.invoke(cli, ["extract", "-q", "-f", "json", text])
        explicit = runner.invoke(cli, ["extract", "-q", "-f", "json", "-m", "standard", text])

        assert "dangerous" not in json.loads(configured.output)["extracted"]["text"]
        assert "dangerous" in json.loads(explicit.output)["extracted"]["text"]


class TestCLISources:
    """Tests for how SOURCE arguments are resolved."""

    def test_reads_stdin(self, runner):
        """Test "-" reads the article from standard input."""
        result = runner.invoke(
            cli, ["extract", "-q", "-f", "json", "-"], input=LONG_ARTICLE
        )
        assert result.exit_code == 0, result.output
        assert "$89.5 billion" in json.loads(result.output)["extracted"]["text"]

    def test_reads_file(self, runner, tmp_path):
        """Test a file path is read from disk."""
        path = tmp_path / "article.txt"
        path.write_text(LONG_ARTICLE, encoding="utf-8")
        result = runner.invoke(cli, ["extract", "-q", "-f", "json", str(path)])
        assert "$89.5 billion" in json.loads(result.output)["extracted"]["text"]

    def test_long_raw_text_is_not_a_path(self, runner):
        """Test text longer than a file name is extracted, not an OS error."""
        text = LONG_ARTICLE * 3
        assert len(text.encode()) > 255
        result = runner.invoke(cli, ["extract", "-q", "-f", "json", text])
        assert result.exit_code == 0, result.output
