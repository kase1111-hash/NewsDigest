"""Slack integration for NewsDigest.

Sends digests and allows interaction via Slack.
Uses the Slack Web API directly (no external dependencies).
"""

from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from typing import Any

import httpx


@dataclass
class SlackUser:
    """A Slack user."""

    id: str
    name: str
    real_name: str | None = None
    is_bot: bool = False


@dataclass
class SlackChannel:
    """A Slack channel."""

    id: str
    name: str
    is_private: bool = False
    is_im: bool = False


@dataclass
class SlackMessage:
    """A Slack message."""

    ts: str  # Timestamp (message ID)
    channel: str
    text: str
    user: str | None = None
    thread_ts: str | None = None
    blocks: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class SlackConfig:
    """Slack bot configuration."""

    bot_token: str  # xoxb-...
    app_token: str | None = None  # xapp-... for Socket Mode
    signing_secret: str | None = None
    default_channel: str | None = None


MessageHandler = Callable[[SlackMessage], Coroutine[Any, Any, None]]


class SlackBot:
    """Slack bot for NewsDigest.

    Provides Slack integration:
    - Send digests to channels
    - Respond to slash commands
    - Handle message mentions

    Example:
        >>> bot = SlackBot(bot_token="xoxb-...")
        >>> await bot.send_message(channel="#news", text="Hello!")
        >>> await bot.send_digest(channel="#news", digest_content="...")
    """

    BASE_URL = "https://slack.com/api"

    def __init__(
        self,
        bot_token: str,
        config: SlackConfig | None = None,
    ) -> None:
        """Initialize Slack bot.

        Args:
            bot_token: Slack bot token (xoxb-...).
            config: Optional configuration.
        """
        if config:
            self.config = config
        else:
            self.config = SlackConfig(bot_token=bot_token)

        self._client = httpx.AsyncClient(
            headers={
                "Authorization": f"Bearer {self.config.bot_token}",
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )
        self._handlers: dict[str, MessageHandler] = {}
        self._bot_user_id: str | None = None

    async def send_message(
        self,
        channel: str,
        text: str,
        blocks: list[dict[str, Any]] | None = None,
        thread_ts: str | None = None,
        unfurl_links: bool = False,
    ) -> SlackMessage | None:
        """Send a message to a channel.

        Args:
            channel: Channel ID or name (e.g., "#general" or "C1234567890").
            text: Message text (used as fallback if blocks provided).
            blocks: Slack Block Kit blocks for rich formatting.
            thread_ts: Reply in thread (timestamp of parent message).
            unfurl_links: Expand URL previews.

        Returns:
            Sent message or None if failed.
        """
        data: dict[str, Any] = {
            "channel": channel,
            "text": text,
            "unfurl_links": unfurl_links,
        }

        if blocks:
            data["blocks"] = blocks

        if thread_ts:
            data["thread_ts"] = thread_ts

        response = await self._client.post(
            f"{self.BASE_URL}/chat.postMessage",
            json=data,
        )

        result = response.json()
        if not result.get("ok"):
            return None

        return SlackMessage(
            ts=result.get("ts", ""),
            channel=result.get("channel", channel),
            text=text,
        )

    async def send_digest(
        self,
        channel: str,
        digest_content: str,
        title: str | None = None,
        thread_ts: str | None = None,
    ) -> bool:
        """Send a formatted digest to a channel.

        Args:
            channel: Target channel.
            digest_content: Digest content (markdown).
            title: Optional title.
            thread_ts: Optional thread to reply in.

        Returns:
            True if sent successfully.
        """
        blocks = self._build_digest_blocks(digest_content, title)

        # Slack has a limit of 50 blocks per message
        if len(blocks) > 50:
            # Send in multiple messages
            for i in range(0, len(blocks), 50):
                chunk = blocks[i : i + 50]
                message = await self.send_message(
                    channel=channel,
                    text=digest_content[:3000],
                    blocks=chunk,
                    thread_ts=thread_ts,
                )
                if not message:
                    return False
            return True

        message = await self.send_message(
            channel=channel,
            text=digest_content[:3000],
            blocks=blocks,
            thread_ts=thread_ts,
        )

        return message is not None

    async def broadcast_digest(
        self,
        digest_content: str,
        channels: list[str] | None = None,
        title: str | None = None,
    ) -> dict[str, bool]:
        """Send digest to multiple channels.

        Args:
            digest_content: Digest content.
            channels: List of channels (uses default if not provided).
            title: Optional title.

        Returns:
            Dict mapping channel to success status.
        """
        if not channels:
            if self.config.default_channel:
                channels = [self.config.default_channel]
            else:
                return {}

        results = {}
        for channel in channels:
            results[channel] = await self.send_digest(
                channel=channel,
                digest_content=digest_content,
                title=title,
            )

        return results

    async def update_message(
        self,
        channel: str,
        ts: str,
        text: str,
        blocks: list[dict[str, Any]] | None = None,
    ) -> bool:
        """Update an existing message.

        Args:
            channel: Channel containing the message.
            ts: Message timestamp (ID).
            text: New text content.
            blocks: New blocks content.

        Returns:
            True if updated successfully.
        """
        data: dict[str, Any] = {
            "channel": channel,
            "ts": ts,
            "text": text,
        }

        if blocks:
            data["blocks"] = blocks

        response = await self._client.post(
            f"{self.BASE_URL}/chat.update",
            json=data,
        )

        result = response.json()
        ok: bool = result.get("ok", False)
        return ok

    async def add_reaction(
        self,
        channel: str,
        ts: str,
        emoji: str,
    ) -> bool:
        """Add a reaction to a message.

        Args:
            channel: Channel containing the message.
            ts: Message timestamp.
            emoji: Emoji name (without colons).

        Returns:
            True if added successfully.
        """
        response = await self._client.post(
            f"{self.BASE_URL}/reactions.add",
            json={
                "channel": channel,
                "timestamp": ts,
                "name": emoji,
            },
        )

        result = response.json()
        ok: bool = result.get("ok", False)
        return ok

    async def get_channel_history(
        self,
        channel: str,
        limit: int = 100,
    ) -> list[SlackMessage]:
        """Get recent messages from a channel.

        Args:
            channel: Channel ID.
            limit: Maximum messages to return.

        Returns:
            List of messages.
        """
        response = await self._client.get(
            f"{self.BASE_URL}/conversations.history",
            params={
                "channel": channel,
                "limit": limit,
            },
        )

        result = response.json()
        if not result.get("ok"):
            return []

        messages = [
            SlackMessage(
                ts=msg.get("ts", ""),
                channel=channel,
                text=msg.get("text", ""),
                user=msg.get("user"),
                thread_ts=msg.get("thread_ts"),
                blocks=msg.get("blocks", []),
            )
            for msg in result.get("messages", [])
        ]

        return messages

    async def get_bot_info(self) -> SlackUser | None:
        """Get bot user information.

        Returns:
            Bot user info or None.
        """
        response = await self._client.get(f"{self.BASE_URL}/auth.test")

        result = response.json()
        if not result.get("ok"):
            return None

        self._bot_user_id = result.get("user_id")

        return SlackUser(
            id=result.get("user_id", ""),
            name=result.get("user", ""),
            is_bot=True,
        )

    async def list_channels(
        self,
        types: str = "public_channel,private_channel",
    ) -> list[SlackChannel]:
        """List available channels.

        Args:
            types: Channel types to include.

        Returns:
            List of channels.
        """
        response = await self._client.get(
            f"{self.BASE_URL}/conversations.list",
            params={"types": types},
        )

        result = response.json()
        if not result.get("ok"):
            return []

        channels = [
            SlackChannel(
                id=ch.get("id", ""),
                name=ch.get("name", ""),
                is_private=ch.get("is_private", False),
                is_im=ch.get("is_im", False),
            )
            for ch in result.get("channels", [])
        ]

        return channels

    def _build_digest_blocks(
        self,
        content: str,
        title: str | None = None,
    ) -> list[dict[str, Any]]:
        """Build Slack blocks from digest content.

        Args:
            content: Markdown digest content.
            title: Optional title.

        Returns:
            List of Slack blocks.
        """
        blocks: list[dict[str, Any]] = []

        if title:
            blocks.append(
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": title,
                        "emoji": True,
                    },
                }
            )

        # Parse markdown content into sections
        current_section = ""
        for raw_line in content.split("\n"):
            line = raw_line.strip()

            if line.startswith("## "):
                # New section header
                if current_section:
                    blocks.append(
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": current_section[:3000],
                            },
                        }
                    )
                    current_section = ""

                blocks.append({"type": "divider"})
                blocks.append(
                    {
                        "type": "header",
                        "text": {
                            "type": "plain_text",
                            "text": line[3:],
                            "emoji": True,
                        },
                    }
                )

            elif line.startswith("### "):
                if current_section:
                    blocks.append(
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": current_section[:3000],
                            },
                        }
                    )
                    current_section = ""

                current_section = f"*{line[4:]}*\n"

            elif line:
                current_section += f"{line}\n"

        # Add remaining content
        if current_section:
            blocks.append(
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": current_section[:3000],
                    },
                }
            )

        return blocks

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()

    async def __aenter__(self) -> "SlackBot":
        """Async context manager entry."""
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Async context manager exit."""
        await self.close()


class SlackSlashCommandHandler:
    """Handle Slack slash commands.

    Designed to work with a web framework (FastAPI, Flask, etc.)
    to receive slash command webhooks.

    Example with FastAPI:
        >>> handler = SlackSlashCommandHandler(signing_secret="...")
        >>> @app.post("/slack/commands")
        >>> async def handle_command(request: Request):
        ...     return await handler.handle(request)
    """

    def __init__(
        self,
        signing_secret: str,
        bot: SlackBot | None = None,
    ) -> None:
        """Initialize handler.

        Args:
            signing_secret: Slack signing secret for verification.
            bot: Optional SlackBot for responses.
        """
        self.signing_secret = signing_secret
        self.bot = bot
        self._commands: dict[str, MessageHandler] = {}

    def register_command(self, command: str, handler: MessageHandler) -> None:
        """Register a slash command handler.

        Args:
            command: Command name (e.g., "/newsdigest").
            handler: Async handler function.
        """
        self._commands[command.lower()] = handler

    async def handle_request(
        self,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        """Handle a slash command request.

        Args:
            body: Parsed form data from Slack.

        Returns:
            Response to send back to Slack.
        """
        command = body.get("command", "").lower()
        text = body.get("text", "")
        user_id = body.get("user_id", "")
        channel_id = body.get("channel_id", "")

        handler = self._commands.get(command)
        if not handler:
            return {
                "response_type": "ephemeral",
                "text": f"Unknown command: {command}",
            }

        # Create a mock message for the handler
        message = SlackMessage(
            ts="",
            channel=channel_id,
            text=text,
            user=user_id,
        )

        try:
            await handler(message)
            return {
                "response_type": "in_channel",
                "text": "Processing...",
            }
        except Exception as e:
            return {
                "response_type": "ephemeral",
                "text": f"Error: {e}",
            }


def create_newsdigest_slack_bot(
    bot_token: str,
    default_channel: str | None = None,
    extractor: Any = None,
    digest_generator: Any = None,
) -> SlackBot:
    """Create a pre-configured NewsDigest Slack bot.

    Args:
        bot_token: Slack bot token.
        default_channel: Default channel for digests.
        extractor: Optional Extractor instance.
        digest_generator: Optional DigestGenerator instance.

    Returns:
        Configured SlackBot instance.
    """
    config = SlackConfig(
        bot_token=bot_token,
        default_channel=default_channel,
    )

    return SlackBot(bot_token, config=config)
