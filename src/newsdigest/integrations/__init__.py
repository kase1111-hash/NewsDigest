"""External integrations for NewsDigest.

This module provides integrations with external services:
- Email delivery for digest distribution
- NewsAPI for fetching articles
- Twitter/X for social media monitoring
- Telegram bot for messaging
- Slack bot for workspace integration

Each integration has optional dependencies that must be installed separately:
    pip install newsdigest[email]      # Email (aiosmtplib)
    pip install newsdigest[newsapi]    # NewsAPI (newsapi-python)
    pip install newsdigest[twitter]    # Twitter (tweepy)
    pip install newsdigest[full]       # All integrations
"""

from newsdigest.integrations.email import (
    DigestEmailScheduler,
    EmailConfig,
    EmailMessage,
    EmailSender,
)
from newsdigest.integrations.newsapi import (
    NewsAPIArticle,
    NewsAPIClient,
    NewsAPIConfig,
    NewsAPIIngestor,
)
from newsdigest.integrations.slack import (
    SlackBot,
    SlackChannel,
    SlackConfig,
    SlackMessage,
    SlackSlashCommandHandler,
    SlackUser,
    create_newsdigest_slack_bot,
)
from newsdigest.integrations.telegram import (
    TelegramBot,
    TelegramChat,
    TelegramConfig,
    TelegramMessage,
    TelegramUser,
    create_newsdigest_bot,
)
from newsdigest.integrations.twitter import (
    Tweet,
    TwitterClient,
    TwitterConfig,
    TwitterIngestor,
)


__all__ = [
    "DigestEmailScheduler",
    "EmailConfig",
    "EmailMessage",
    "EmailSender",
    "NewsAPIArticle",
    "NewsAPIClient",
    "NewsAPIConfig",
    "NewsAPIIngestor",
    "SlackBot",
    "SlackChannel",
    "SlackConfig",
    "SlackMessage",
    "SlackSlashCommandHandler",
    "SlackUser",
    "TelegramBot",
    "TelegramChat",
    "TelegramConfig",
    "TelegramMessage",
    "TelegramUser",
    "Tweet",
    "TwitterClient",
    "TwitterConfig",
    "TwitterIngestor",
    "create_newsdigest_bot",
    "create_newsdigest_slack_bot",
]
