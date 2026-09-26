"""Secure secrets management for NewsDigest.

This module provides secure handling of sensitive configuration:
- Environment variable loading with validation
- .env file support (using python-dotenv if available)
- Secret masking for logging
- Optional integration with external secrets managers
"""

import os
import re
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

from newsdigest.utils.logging import get_logger


logger = get_logger(__name__)

T = TypeVar("T")


# =============================================================================
# SECRET VALUE CLASS
# =============================================================================


class SecretValue:
    """A wrapper for secret values that prevents accidental exposure.

    The value is hidden in string representations but accessible via .get().

    Usage:
        secret = SecretValue("my-api-key")
        print(secret)  # Output: SecretValue(****)
        actual = secret.get()  # Returns "my-api-key"
    """

    def __init__(self, value: str | None) -> None:
        """Initialize secret value.

        Args:
            value: The secret value to wrap.
        """
        self._value = value

    def get(self) -> str | None:
        """Get the actual secret value.

        Returns:
            The secret value.
        """
        return self._value

    def __str__(self) -> str:
        """Return masked representation."""
        if self._value is None:
            return "SecretValue(None)"
        return "SecretValue(****)"

    def __repr__(self) -> str:
        """Return masked representation."""
        return self.__str__()

    def __bool__(self) -> bool:
        """Check if secret has a value."""
        return self._value is not None and len(self._value) > 0

    def __eq__(self, other: object) -> bool:
        """Compare secret values."""
        if isinstance(other, SecretValue):
            return self._value == other._value
        return False

    def __hash__(self) -> int:
        """Hash based on value."""
        return hash(self._value)


# =============================================================================
# ENVIRONMENT LOADER
# =============================================================================


class EnvLoader:
    """Loads and validates environment variables with .env file support."""

    def __init__(
        self,
        env_file: str | Path | None = None,
        prefix: str = "NEWSDIGEST_",
    ) -> None:
        """Initialize environment loader.

        Args:
            env_file: Path to .env file. If None, searches for .env in cwd.
            prefix: Prefix for environment variables.
        """
        self._prefix = prefix
        self._loaded_from_file = False
        self._env_file: Path | None = None

        # Try to load .env file
        if env_file:
            self._env_file = Path(env_file)
        else:
            # Search for .env in current directory and parents
            self._env_file = self._find_env_file()

        if self._env_file and self._env_file.exists():
            self._load_env_file(self._env_file)

    def _find_env_file(self) -> Path | None:
        """Find .env file in current directory or parents.

        Returns:
            Path to .env file or None.
        """
        current = Path.cwd()
        for _ in range(5):  # Search up to 5 levels
            env_path = current / ".env"
            if env_path.exists():
                return env_path
            parent = current.parent
            if parent == current:
                break
            current = parent
        return None

    def _load_env_file(self, path: Path) -> None:
        """Load environment variables from .env file.

        Args:
            path: Path to .env file.
        """
        try:
            # Try using python-dotenv if available
            try:
                from dotenv import load_dotenv
                load_dotenv(path, override=False)
                self._loaded_from_file = True
                logger.debug(f"Loaded environment from {path} using python-dotenv")
                return
            except ImportError:
                pass

            # Fallback: manual parsing
            self._parse_env_file(path)
            self._loaded_from_file = True
            logger.debug(f"Loaded environment from {path} using manual parser")

        except Exception as e:
            logger.warning(f"Failed to load .env file {path}: {e}")

    def _parse_env_file(self, path: Path) -> None:
        """Parse .env file manually.

        Args:
            path: Path to .env file.
        """
        with open(path, encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()

                # Skip empty lines and comments
                if not line or line.startswith("#"):
                    continue

                # Parse KEY=VALUE
                if "=" not in line:
                    logger.warning(f".env line {line_num}: Invalid format (missing =)")
                    continue

                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip()

                # Remove surrounding quotes; only double-quoted values
                # interpret escape sequences (as with python-dotenv)
                if len(value) >= 2 and value[0] == value[-1] == '"':
                    value = value[1:-1].encode().decode("unicode_escape")
                elif len(value) >= 2 and value[0] == value[-1] == "'":
                    value = value[1:-1]

                # Only set if not already in environment (don't override)
                if key not in os.environ:
                    os.environ[key] = value

    def get(
        self,
        key: str,
        default: T | None = None,
        required: bool = False,
        cast: Callable[[str], T] | None = None,
    ) -> str | T | None:
        """Get an environment variable.

        Args:
            key: Variable name (without prefix).
            default: Default value if not set.
            required: If True, raises ValueError if not set.
            cast: Optional function to cast the value.

        Returns:
            The environment variable value.

        Raises:
            ValueError: If required and not set.
        """
        full_key = f"{self._prefix}{key}"
        value = os.environ.get(full_key)

        # Also check without prefix for common vars
        if value is None and not key.startswith(self._prefix):
            value = os.environ.get(key)

        if value is None:
            if required:
                raise ValueError(f"Required environment variable {full_key} is not set")
            return default

        if cast:
            try:
                return cast(value)
            except (ValueError, TypeError) as e:
                if required:
                    raise ValueError(f"Failed to cast {full_key}: {e}")
                return default

        return value

    def get_secret(
        self,
        key: str,
        required: bool = False,
    ) -> SecretValue:
        """Get a secret environment variable.

        Args:
            key: Variable name (without prefix).
            required: If True, raises ValueError if not set.

        Returns:
            SecretValue wrapper.
        """
        value = self.get(key, required=required)
        return SecretValue(value if isinstance(value, str) else None)

    def get_bool(
        self,
        key: str,
        default: bool = False,
    ) -> bool:
        """Get a boolean environment variable.

        Args:
            key: Variable name.
            default: Default value.

        Returns:
            Boolean value.
        """
        value = self.get(key)
        if value is None:
            return default
        return value.lower() in ("true", "1", "yes", "on")

    def get_int(
        self,
        key: str,
        default: int = 0,
    ) -> int:
        """Get an integer environment variable.

        Args:
            key: Variable name.
            default: Default value.

        Returns:
            Integer value.
        """
        result = self.get(key, default=default, cast=int)
        return result if isinstance(result, int) else default

    def get_float(
        self,
        key: str,
        default: float = 0.0,
    ) -> float:
        """Get a float environment variable.

        Args:
            key: Variable name.
            default: Default value.

        Returns:
            Float value.
        """
        result = self.get(key, default=default, cast=float)
        return result if isinstance(result, float) else default

    def get_list(
        self,
        key: str,
        default: list[str] | None = None,
        separator: str = ",",
    ) -> list[str]:
        """Get a list environment variable.

        Args:
            key: Variable name.
            default: Default value.
            separator: List separator.

        Returns:
            List of strings.
        """
        value = self.get(key)
        if value is None:
            return default or []
        return [item.strip() for item in value.split(separator) if item.strip()]

    @property
    def loaded_from_file(self) -> bool:
        """Check if configuration was loaded from .env file."""
        return self._loaded_from_file

    @property
    def env_file_path(self) -> Path | None:
        """Get the path to the loaded .env file."""
        return self._env_file


# =============================================================================
# SECRETS MANAGER INTEGRATION
# =============================================================================


class SecretsManager:
    """Abstract interface for secrets managers.

    Override _fetch_secret to integrate with external secrets managers
    like AWS Secrets Manager, HashiCorp Vault, etc.
    """

    def __init__(self, cache_ttl: int = 300) -> None:
        """Initialize secrets manager.

        Args:
            cache_ttl: Cache time-to-live in seconds.
        """
        self._cache: dict[str, tuple] = {}  # key -> (value, timestamp)
        self._cache_ttl = cache_ttl

    def get_secret(self, key: str, required: bool = False) -> SecretValue:
        """Get a secret value.

        Args:
            key: Secret key/path.
            required: If True, raises if not found.

        Returns:
            SecretValue wrapper.
        """
        import time

        # Check cache
        if key in self._cache:
            value, timestamp = self._cache[key]
            if time.time() - timestamp < self._cache_ttl:
                return SecretValue(value)

        # Fetch from backend
        try:
            value = self._fetch_secret(key)
        except Exception as e:
            logger.error(f"Failed to fetch secret {key}: {e}")
            if required:
                raise ValueError(f"Required secret {key} not found: {e}") from e
            return SecretValue(None)

        if value is None:
            # Not cached, so a secret added later is picked up on next lookup
            if required:
                raise ValueError(f"Required secret {key} not found")
            return SecretValue(None)

        self._cache[key] = (value, time.time())
        return SecretValue(value)

    def _fetch_secret(self, key: str) -> str | None:
        """Fetch secret from backend.

        Override this method to integrate with external secrets managers.

        Args:
            key: Secret key/path.

        Returns:
            Secret value or None.
        """
        # Default implementation: fall back to environment
        return os.environ.get(key)

    def clear_cache(self) -> None:
        """Clear the secrets cache."""
        self._cache.clear()


class AWSSecretsManager(SecretsManager):
    """AWS Secrets Manager integration.

    Requires boto3: pip install boto3
    """

    def __init__(
        self,
        region_name: str | None = None,
        cache_ttl: int = 300,
    ) -> None:
        """Initialize AWS Secrets Manager client.

        Args:
            region_name: AWS region.
            cache_ttl: Cache TTL in seconds.
        """
        super().__init__(cache_ttl)
        self._region = region_name or os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
        self._client = None

    def _get_client(self):
        """Get or create boto3 client."""
        if self._client is None:
            try:
                import boto3
                self._client = boto3.client(
                    "secretsmanager",
                    region_name=self._region,
                )
            except ImportError:
                raise ImportError("boto3 is required for AWS Secrets Manager")
        return self._client

    def _fetch_secret(self, key: str) -> str | None:
        """Fetch secret from AWS Secrets Manager.

        Args:
            key: Secret name or ARN.

        Returns:
            Secret value.
        """
        try:
            client = self._get_client()
            response = client.get_secret_value(SecretId=key)

            if "SecretString" in response:
                return response["SecretString"]
            else:
                import base64
                return base64.b64decode(response["SecretBinary"]).decode("utf-8")

        except Exception as e:
            logger.debug(f"AWS Secrets Manager lookup failed for {key}: {e}")
            # Fall back to environment
            return os.environ.get(key)


# =============================================================================
# SECRET MASKING
# =============================================================================


class SecretMasker:
    """Masks secrets in strings to prevent accidental exposure in logs."""

    def __init__(self) -> None:
        """Initialize secret masker."""
        self._secrets: list[str] = []
        self._patterns: list[re.Pattern] = []

        # Common secret patterns
        self._add_pattern(r"(?i)(api[_-]?key|apikey)['\"]?\s*[:=]\s*['\"]?([a-zA-Z0-9_\-]{16,})")
        self._add_pattern(r"(?i)(secret|token|password|passwd|pwd)['\"]?\s*[:=]\s*['\"]?([^\s'\"]{8,})")
        self._add_pattern(r"(?i)(bearer\s+)([a-zA-Z0-9_\-\.]+)")
        self._add_pattern(r"(sk-[a-zA-Z0-9_\-]{20,})")  # OpenAI keys (incl. sk-proj-)
        self._add_pattern(r"(ghp_[a-zA-Z0-9]{36,})")  # GitHub tokens
        self._add_pattern(r"(xox[baprs]-[a-zA-Z0-9\-]+)")  # Slack tokens

    def _add_pattern(self, pattern: str) -> None:
        """Add a regex pattern for secret detection."""
        self._patterns.append(re.compile(pattern))

    def register_secret(self, secret: str) -> None:
        """Register a secret value to be masked.

        Args:
            secret: Secret value to mask.
        """
        if secret and len(secret) >= 4:
            self._secrets.append(secret)

    def mask(self, text: str) -> str:
        """Mask secrets in text.

        Args:
            text: Text that may contain secrets.

        Returns:
            Text with secrets masked.
        """
        result = text

        # Mask registered secrets
        for secret in self._secrets:
            if secret in result:
                # Keep first 2 and last 2 characters for identification
                if len(secret) > 8:
                    masked = f"{secret[:2]}****{secret[-2:]}"
                else:
                    masked = "****"
                result = result.replace(secret, masked)

        # Mask pattern-matched secrets
        for pattern in self._patterns:
            def replacer(match):
                groups = match.groups()
                if len(groups) >= 2:
                    # Keep prefix, mask the secret part
                    return f"{groups[0]}****"
                return "****"

            result = pattern.sub(replacer, result)

        return result


# =============================================================================
# GLOBAL INSTANCES
# =============================================================================

# Global environment loader
_env_loader: EnvLoader | None = None

# Global secret masker
_masker = SecretMasker()


def get_env_loader() -> EnvLoader:
    """Get the global environment loader.

    Returns:
        EnvLoader instance.
    """
    global _env_loader
    if _env_loader is None:
        _env_loader = EnvLoader()
    return _env_loader


def init_env(
    env_file: str | Path | None = None,
    prefix: str = "NEWSDIGEST_",
) -> EnvLoader:
    """Initialize the global environment loader.

    Args:
        env_file: Path to .env file.
        prefix: Environment variable prefix.

    Returns:
        EnvLoader instance.
    """
    global _env_loader
    _env_loader = EnvLoader(env_file=env_file, prefix=prefix)
    return _env_loader


def get_secret_masker() -> SecretMasker:
    """Get the global secret masker.

    Returns:
        SecretMasker instance.
    """
    return _masker


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================


def get_env(
    key: str,
    default: str | None = None,
    required: bool = False,
) -> str | None:
    """Get an environment variable.

    Args:
        key: Variable name.
        default: Default value.
        required: If True, raises if not set.

    Returns:
        Environment variable value.
    """
    result = get_env_loader().get(key, default=default, required=required)
    return result if isinstance(result, str) else default


def get_secret(key: str, required: bool = False) -> SecretValue:
    """Get a secret environment variable.

    Args:
        key: Variable name.
        required: If True, raises if not set.

    Returns:
        SecretValue wrapper.
    """
    return get_env_loader().get_secret(key, required=required)


def mask_secrets(text: str) -> str:
    """Mask secrets in text.

    Args:
        text: Text to mask.

    Returns:
        Masked text.
    """
    return _masker.mask(text)


def register_secret(secret: str) -> None:
    """Register a secret for masking.

    Args:
        secret: Secret value.
    """
    _masker.register_secret(secret)
