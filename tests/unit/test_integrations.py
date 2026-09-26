"""Tests for integration factory helpers."""

from newsdigest.integrations.slack import SlackBot, create_newsdigest_slack_bot


class TestSlackFactory:
    """Tests for create_newsdigest_slack_bot."""

    def test_builds_bot_from_token(self) -> None:
        """Test the factory passes the token through (it used to raise TypeError)."""
        bot = create_newsdigest_slack_bot("xoxb-test", default_channel="#news")

        assert isinstance(bot, SlackBot)
        assert bot.config.bot_token == "xoxb-test"
        assert bot.config.default_channel == "#news"
