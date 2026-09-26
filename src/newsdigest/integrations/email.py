"""Email delivery integration for NewsDigest.

Sends digest summaries via email using SMTP or async SMTP.
Requires: pip install newsdigest[email]
"""

import smtplib
import ssl
from dataclasses import dataclass, field
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    import asyncio


try:
    import aiosmtplib

    HAS_AIOSMTPLIB = True
except ImportError:
    HAS_AIOSMTPLIB = False


@dataclass
class EmailConfig:
    """Email server configuration."""

    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    username: str = ""
    password: str = ""
    from_email: str = ""
    from_name: str = "NewsDigest"
    use_tls: bool = True
    use_ssl: bool = False
    timeout: int = 30


@dataclass
class EmailMessage:
    """Email message to send."""

    to: list[str]
    subject: str
    body_text: str
    body_html: str | None = None
    cc: list[str] = field(default_factory=list)
    bcc: list[str] = field(default_factory=list)
    reply_to: str | None = None


class EmailSender:
    """Send emails with digest content.

    Supports both synchronous (smtplib) and asynchronous (aiosmtplib)
    sending for flexibility in different contexts.

    Example:
        >>> config = EmailConfig(
        ...     smtp_host="smtp.gmail.com",
        ...     username="your@email.com",
        ...     password="app-password",
        ...     from_email="your@email.com",
        ... )
        >>> sender = EmailSender(config)
        >>> await sender.send_digest(
        ...     to=["recipient@example.com"],
        ...     digest_content="# Today's News...",
        ... )
    """

    def __init__(self, config: EmailConfig) -> None:
        """Initialize email sender.

        Args:
            config: Email server configuration.
        """
        self.config = config

    def send(self, message: EmailMessage) -> bool:
        """Send an email synchronously.

        Args:
            message: The email message to send.

        Returns:
            True if sent successfully.

        Raises:
            ConnectionError: If unable to connect to SMTP server.
            ValueError: If configuration is invalid.
        """
        if not self.config.username or not self.config.password:
            raise ValueError("SMTP username and password are required")

        msg = self._build_mime_message(message)

        try:
            if self.config.use_ssl:
                context = ssl.create_default_context()
                with smtplib.SMTP_SSL(
                    self.config.smtp_host,
                    self.config.smtp_port,
                    context=context,
                    timeout=self.config.timeout,
                ) as server:
                    server.login(self.config.username, self.config.password)
                    server.send_message(msg)
            else:
                with smtplib.SMTP(
                    self.config.smtp_host,
                    self.config.smtp_port,
                    timeout=self.config.timeout,
                ) as server:
                    if self.config.use_tls:
                        server.starttls()
                    server.login(self.config.username, self.config.password)
                    server.send_message(msg)

            return True

        except smtplib.SMTPException as e:
            raise ConnectionError(f"Failed to send email: {e}") from e

    async def send_async(self, message: EmailMessage) -> bool:
        """Send an email asynchronously.

        Requires aiosmtplib to be installed.

        Args:
            message: The email message to send.

        Returns:
            True if sent successfully.

        Raises:
            ImportError: If aiosmtplib is not installed.
            ConnectionError: If unable to connect to SMTP server.
        """
        if not HAS_AIOSMTPLIB:
            raise ImportError(
                "aiosmtplib is required for async email. "
                "Install with: pip install newsdigest[email]"
            )

        if not self.config.username or not self.config.password:
            raise ValueError("SMTP username and password are required")

        msg = self._build_mime_message(message)

        try:
            await aiosmtplib.send(
                msg,
                hostname=self.config.smtp_host,
                port=self.config.smtp_port,
                username=self.config.username,
                password=self.config.password,
                start_tls=self.config.use_tls,
                use_tls=self.config.use_ssl,
                timeout=self.config.timeout,
            )
            return True

        except aiosmtplib.SMTPException as e:
            raise ConnectionError(f"Failed to send email: {e}") from e

    def send_digest(
        self,
        to: list[str],
        digest_content: str,
        subject: str | None = None,
        format: str = "markdown",
    ) -> bool:
        """Send a digest email synchronously.

        Args:
            to: List of recipient email addresses.
            digest_content: The digest content to send.
            subject: Email subject (default: "Your NewsDigest Summary").
            format: Content format ('markdown', 'text', 'html').

        Returns:
            True if sent successfully.
        """
        subject = subject or "Your NewsDigest Summary"

        if format == "html":
            body_html = digest_content
            body_text = self._html_to_text(digest_content)
        elif format == "markdown":
            body_text = digest_content
            body_html = self._markdown_to_html(digest_content)
        else:
            body_text = digest_content
            body_html = None

        message = EmailMessage(
            to=to,
            subject=subject,
            body_text=body_text,
            body_html=body_html,
        )

        return self.send(message)

    async def send_digest_async(
        self,
        to: list[str],
        digest_content: str,
        subject: str | None = None,
        format: str = "markdown",
    ) -> bool:
        """Send a digest email asynchronously.

        Args:
            to: List of recipient email addresses.
            digest_content: The digest content to send.
            subject: Email subject (default: "Your NewsDigest Summary").
            format: Content format ('markdown', 'text', 'html').

        Returns:
            True if sent successfully.
        """
        subject = subject or "Your NewsDigest Summary"

        if format == "html":
            body_html = digest_content
            body_text = self._html_to_text(digest_content)
        elif format == "markdown":
            body_text = digest_content
            body_html = self._markdown_to_html(digest_content)
        else:
            body_text = digest_content
            body_html = None

        message = EmailMessage(
            to=to,
            subject=subject,
            body_text=body_text,
            body_html=body_html,
        )

        return await self.send_async(message)

    def _build_mime_message(self, message: EmailMessage) -> MIMEMultipart:
        """Build a MIME message from EmailMessage.

        Args:
            message: The email message.

        Returns:
            MIME multipart message.
        """
        msg = MIMEMultipart("alternative")
        msg["Subject"] = message.subject
        msg["From"] = f"{self.config.from_name} <{self.config.from_email}>"
        msg["To"] = ", ".join(message.to)

        if message.cc:
            msg["Cc"] = ", ".join(message.cc)

        if message.reply_to:
            msg["Reply-To"] = message.reply_to

        # Attach text version
        msg.attach(MIMEText(message.body_text, "plain", "utf-8"))

        # Attach HTML version if provided
        if message.body_html:
            msg.attach(MIMEText(message.body_html, "html", "utf-8"))

        return msg

    def _markdown_to_html(self, markdown: str) -> str:
        """Convert markdown to basic HTML.

        Args:
            markdown: Markdown text.

        Returns:
            HTML string.
        """
        html_lines = []
        in_list = False

        for raw_line in markdown.split("\n"):
            line = raw_line.rstrip()

            # Headers
            if line.startswith("### "):
                html_lines.append(f"<h3>{line[4:]}</h3>")
            elif line.startswith("## "):
                html_lines.append(f"<h2>{line[3:]}</h2>")
            elif line.startswith("# "):
                html_lines.append(f"<h1>{line[2:]}</h1>")
            # List items
            elif line.startswith("- ") or line.startswith("* "):
                if not in_list:
                    html_lines.append("<ul>")
                    in_list = True
                html_lines.append(f"<li>{line[2:]}</li>")
            # Bold
            elif "**" in line:
                import re

                line = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", line)
                html_lines.append(f"<p>{line}</p>")
            # Empty line
            elif not line:
                if in_list:
                    html_lines.append("</ul>")
                    in_list = False
                html_lines.append("<br>")
            # Regular paragraph
            else:
                html_lines.append(f"<p>{line}</p>")

        if in_list:
            html_lines.append("</ul>")

        return "\n".join(html_lines)

    def _html_to_text(self, html: str) -> str:
        """Convert HTML to plain text.

        Args:
            html: HTML string.

        Returns:
            Plain text string.
        """
        import re

        # Remove tags
        text = re.sub(r"<[^>]+>", "", html)
        # Convert entities
        text = text.replace("&nbsp;", " ")
        text = text.replace("&amp;", "&")
        text = text.replace("&lt;", "<")
        text = text.replace("&gt;", ">")
        # Clean up whitespace
        text = re.sub(r"\n\s*\n", "\n\n", text)
        return text.strip()


class DigestEmailScheduler:
    """Schedule and send periodic digest emails.

    Example:
        >>> scheduler = DigestEmailScheduler(
        ...     sender=EmailSender(config),
        ...     recipients=["user@example.com"],
        ... )
        >>> scheduler.schedule_daily(hour=8, minute=0)
    """

    def __init__(
        self,
        sender: EmailSender,
        recipients: list[str],
    ) -> None:
        """Initialize scheduler.

        Args:
            sender: Email sender instance.
            recipients: List of recipient emails.
        """
        self.sender = sender
        self.recipients = recipients
        self._running = False
        self._task: asyncio.Task[None] | None = None

    async def send_now(
        self,
        digest_content: str,
        subject: str | None = None,
    ) -> bool:
        """Send digest immediately.

        Args:
            digest_content: The digest content.
            subject: Optional custom subject.

        Returns:
            True if sent successfully.
        """
        return await self.sender.send_digest_async(
            to=self.recipients,
            digest_content=digest_content,
            subject=subject,
        )

    def add_recipient(self, email: str) -> None:
        """Add a recipient.

        Args:
            email: Email address to add.
        """
        if email not in self.recipients:
            self.recipients.append(email)

    def remove_recipient(self, email: str) -> bool:
        """Remove a recipient.

        Args:
            email: Email address to remove.

        Returns:
            True if removed, False if not found.
        """
        if email in self.recipients:
            self.recipients.remove(email)
            return True
        return False
