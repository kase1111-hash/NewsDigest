"""Telegram bot integration for NewsDigest.

Sends digests and allows interaction via Telegram.
Uses the Telegram Bot API directly (no external dependencies).
"""

import asyncio
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx


@dataclass
class TelegramUser:
    """A Telegram user."""

    id: int
    is_bot: bool = False
    first_name: str = ""
    last_name: str | None = None
    username: str | None = None
    language_code: str | None = None


@dataclass
class TelegramChat:
    """A Telegram chat."""

    id: int
    type: str  # private, group, supergroup, channel
    title: str | None = None
    username: str | None = None


@dataclass
class TelegramMessage:
    """A Telegram message."""

    message_id: int
    chat: TelegramChat
    date: datetime
    text: str | None = None
    from_user: TelegramUser | None = None
    reply_to_message: "TelegramMessage | None" = None


@dataclass
class TelegramConfig:
    """Telegram bot configuration."""

    bot_token: str
    allowed_users: list[int] = field(default_factory=list)
    allowed_chats: list[int] = field(default_factory=list)
    parse_mode: str = "Markdown"  # Markdown, MarkdownV2, HTML


MessageHandler = Callable[[TelegramMessage], Coroutine[Any, Any, None]]


class TelegramBot:
    """Telegram bot for NewsDigest.

    Provides two-way interaction:
    - Send digests to users/channels
    - Receive commands to generate on-demand extractions

    Example:
        >>> bot = TelegramBot(bot_token="123456:ABC...")
        >>> await bot.send_message(chat_id=12345, text="Hello!")
        >>> # Or run as a bot
        >>> bot.on_command("extract", handle_extract)
        >>> await bot.run()
    """

    BASE_URL = "https://api.telegram.org/bot"

    def __init__(
        self,
        bot_token: str,
        config: TelegramConfig | None = None,
    ) -> None:
        """Initialize Telegram bot.

        Args:
            bot_token: Telegram bot token from @BotFather.
            config: Optional configuration.
        """
        if config:
            self.config = config
        else:
            self.config = TelegramConfig(bot_token=bot_token)

        self._base_url = f"{self.BASE_URL}{self.config.bot_token}"
        self._client = httpx.AsyncClient(timeout=30.0)
        self._running = False
        self._offset = 0
        self._handlers: dict[str, MessageHandler] = {}
        self._default_handler: MessageHandler | None = None

    async def send_message(
        self,
        chat_id: int,
        text: str,
        parse_mode: str | None = None,
        disable_notification: bool = False,
        reply_to_message_id: int | None = None,
    ) -> TelegramMessage | None:
        """Send a text message.

        Args:
            chat_id: Target chat ID.
            text: Message text (max 4096 characters).
            parse_mode: Text formatting (Markdown, MarkdownV2, HTML).
            disable_notification: Send silently.
            reply_to_message_id: Reply to specific message.

        Returns:
            Sent message object or None if failed.
        """
        # Split long messages
        if len(text) > 4096:
            chunks = self._split_message(text, 4096)
            last_message = None
            for chunk in chunks:
                last_message = await self.send_message(
                    chat_id=chat_id,
                    text=chunk,
                    parse_mode=parse_mode,
                    disable_notification=disable_notification,
                )
            return last_message

        data: dict[str, Any] = {
            "chat_id": chat_id,
            "text": text,
        }

        if parse_mode or self.config.parse_mode:
            data["parse_mode"] = parse_mode or self.config.parse_mode

        if disable_notification:
            data["disable_notification"] = True

        if reply_to_message_id:
            data["reply_to_message_id"] = reply_to_message_id

        response = await self._client.post(
            f"{self._base_url}/sendMessage",
            json=data,
        )

        if response.status_code != 200:
            return None

        result = response.json()
        if not result.get("ok"):
            return None

        return self._parse_message(result.get("result", {}))

    async def send_digest(
        self,
        chat_id: int,
        digest_content: str,
        title: str | None = None,
    ) -> bool:
        """Send a digest to a chat.

        Args:
            chat_id: Target chat ID.
            digest_content: Digest content (markdown format).
            title: Optional title header.

        Returns:
            True if sent successfully.
        """
        text = f"*{title}*\n\n{digest_content}" if title else digest_content

        message = await self.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode="Markdown",
        )

        return message is not None

    async def broadcast_digest(
        self,
        digest_content: str,
        title: str | None = None,
    ) -> dict[int, bool]:
        """Send digest to all allowed chats.

        Args:
            digest_content: Digest content.
            title: Optional title.

        Returns:
            Dict mapping chat_id to success status.
        """
        results = {}

        for chat_id in self.config.allowed_chats:
            results[chat_id] = await self.send_digest(
                chat_id=chat_id,
                digest_content=digest_content,
                title=title,
            )

        return results

    def on_command(self, command: str, handler: MessageHandler) -> None:
        """Register a command handler.

        Args:
            command: Command name (without /).
            handler: Async function to handle the command.
        """
        self._handlers[command.lower()] = handler

    def on_message(self, handler: MessageHandler) -> None:
        """Register default message handler.

        Args:
            handler: Async function to handle messages.
        """
        self._default_handler = handler

    async def run(self, poll_interval: float = 1.0) -> None:
        """Run the bot, polling for updates.

        Args:
            poll_interval: Seconds between polls.
        """
        self._running = True

        while self._running:
            try:
                updates = await self._get_updates()

                for update in updates:
                    await self._handle_update(update)

            except Exception:
                # Log error, continue running
                pass

            await asyncio.sleep(poll_interval)

    async def stop(self) -> None:
        """Stop the bot."""
        self._running = False

    async def get_me(self) -> TelegramUser | None:
        """Get bot information.

        Returns:
            Bot user info or None if failed.
        """
        response = await self._client.get(f"{self._base_url}/getMe")

        if response.status_code != 200:
            return None

        result = response.json()
        if not result.get("ok"):
            return None

        user_data = result.get("result", {})
        return TelegramUser(
            id=user_data.get("id", 0),
            is_bot=user_data.get("is_bot", True),
            first_name=user_data.get("first_name", ""),
            username=user_data.get("username"),
        )

    async def _get_updates(self) -> list[dict[str, Any]]:
        """Get updates from Telegram.

        Returns:
            List of update objects.
        """
        params = {
            "offset": self._offset,
            "timeout": 30,
        }

        response = await self._client.get(
            f"{self._base_url}/getUpdates",
            params=params,
            timeout=35.0,
        )

        if response.status_code != 200:
            return []

        result = response.json()
        if not result.get("ok"):
            return []

        updates = result.get("result", [])

        # Update offset
        if updates:
            self._offset = updates[-1]["update_id"] + 1

        return updates

    async def _handle_update(self, update: dict[str, Any]) -> None:
        """Handle a single update.

        Args:
            update: Update object from Telegram.
        """
        message_data = update.get("message")
        if not message_data:
            return

        message = self._parse_message(message_data)
        if not message:
            return

        # Check if user/chat is allowed
        if not self._is_allowed(message):
            return

        # Check for command
        text = message.text or ""
        if text.startswith("/"):
            parts = text[1:].split(maxsplit=1)
            command = parts[0].lower().split("@")[0]  # Remove @botname

            handler = self._handlers.get(command)
            if handler:
                await handler(message)
                return

        # Default handler
        if self._default_handler:
            await self._default_handler(message)

    def _is_allowed(self, message: TelegramMessage) -> bool:
        """Check if message is from allowed user/chat.

        Args:
            message: The message to check.

        Returns:
            True if allowed.
        """
        # If no restrictions, allow all
        if not self.config.allowed_users and not self.config.allowed_chats:
            return True

        # Check chat
        if message.chat.id in self.config.allowed_chats:
            return True

        # Check user
        return bool(
            message.from_user and message.from_user.id in self.config.allowed_users
        )

    def _parse_message(self, data: dict[str, Any]) -> TelegramMessage | None:
        """Parse message from API response.

        Args:
            data: Message data from API.

        Returns:
            TelegramMessage object or None.
        """
        if not data:
            return None

        # Parse chat
        chat_data = data.get("chat", {})
        chat = TelegramChat(
            id=chat_data.get("id", 0),
            type=chat_data.get("type", "private"),
            title=chat_data.get("title"),
            username=chat_data.get("username"),
        )

        # Parse user
        from_data = data.get("from")
        from_user = None
        if from_data:
            from_user = TelegramUser(
                id=from_data.get("id", 0),
                is_bot=from_data.get("is_bot", False),
                first_name=from_data.get("first_name", ""),
                last_name=from_data.get("last_name"),
                username=from_data.get("username"),
                language_code=from_data.get("language_code"),
            )

        # Parse date
        timestamp = data.get("date", 0)
        date = datetime.fromtimestamp(timestamp, tz=UTC)

        return TelegramMessage(
            message_id=data.get("message_id", 0),
            chat=chat,
            date=date,
            text=data.get("text"),
            from_user=from_user,
        )

    def _split_message(self, text: str, max_length: int) -> list[str]:
        """Split long message into chunks.

        Args:
            text: Text to split.
            max_length: Maximum chunk length.

        Returns:
            List of text chunks.
        """
        chunks = []
        current = ""

        for line in text.split("\n"):
            if len(current) + len(line) + 1 > max_length:
                if current:
                    chunks.append(current)
                current = line
            else:
                current = f"{current}\n{line}" if current else line

        if current:
            chunks.append(current)

        return chunks

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()

    async def __aenter__(self) -> "TelegramBot":
        """Async context manager entry."""
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Async context manager exit."""
        await self.close()


def create_newsdigest_bot(
    bot_token: str,
    extractor: Any = None,
    digest_generator: Any = None,
) -> TelegramBot:
    """Create a pre-configured NewsDigest Telegram bot.

    Registers default commands:
    - /extract <url> - Extract content from URL
    - /digest - Generate today's digest
    - /help - Show help message

    Args:
        bot_token: Telegram bot token.
        extractor: Optional Extractor instance.
        digest_generator: Optional DigestGenerator instance.

    Returns:
        Configured TelegramBot instance.
    """
    bot = TelegramBot(bot_token=bot_token)

    async def handle_help(message: TelegramMessage) -> None:
        """Handle /help command."""
        help_text = """*NewsDigest Bot*

Commands:
/extract <url> - Extract and compress content from a URL
/digest - Generate today's news digest
/help - Show this help message

Send me a URL and I'll extract the key information for you!
"""
        await bot.send_message(
            chat_id=message.chat.id,
            text=help_text,
        )

    async def handle_extract(message: TelegramMessage) -> None:
        """Handle /extract command."""
        if not message.text:
            return

        parts = message.text.split(maxsplit=1)
        if len(parts) < 2:
            await bot.send_message(
                chat_id=message.chat.id,
                text="Please provide a URL: /extract <url>",
            )
            return

        url = parts[1].strip()

        await bot.send_message(
            chat_id=message.chat.id,
            text=f"Extracting content from {url}...",
        )

        if extractor:
            try:
                result = await extractor.extract(url)
                response = f"*{result.title or 'Extracted Content'}*\n\n"
                response += result.text[:3000]
                ratio = result.statistics.compression_ratio
                response += f"\n\n_Compression: {ratio:.0%}_"
            except Exception as e:
                response = f"Failed to extract: {e}"
        else:
            response = "Extractor not configured"

        await bot.send_message(
            chat_id=message.chat.id,
            text=response,
        )

    async def handle_digest(message: TelegramMessage) -> None:
        """Handle /digest command."""
        await bot.send_message(
            chat_id=message.chat.id,
            text="Generating digest...",
        )

        if digest_generator:
            try:
                digest = digest_generator.generate(format="markdown")
                await bot.send_digest(
                    chat_id=message.chat.id,
                    digest_content=str(digest),
                    title="Today's News Digest",
                )
            except Exception as e:
                await bot.send_message(
                    chat_id=message.chat.id,
                    text=f"Failed to generate digest: {e}",
                )
        else:
            await bot.send_message(
                chat_id=message.chat.id,
                text="Digest generator not configured",
            )

    bot.on_command("help", handle_help)
    bot.on_command("start", handle_help)
    bot.on_command("extract", handle_extract)
    bot.on_command("digest", handle_digest)

    return bot
