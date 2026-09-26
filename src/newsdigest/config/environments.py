"""Environment-specific configuration management.

This module provides utilities for detecting and loading environment-specific
configurations for development, staging, and production environments.
"""

import os
from enum import Enum
from pathlib import Path
from typing import Any

import yaml

from .settings import Config


class Environment(str, Enum):
    """Supported deployment environments."""

    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"
    TEST = "test"

    @classmethod
    def from_string(cls, value: str) -> "Environment":
        """Parse environment from string.

        Args:
            value: Environment name string.

        Returns:
            Matching Environment enum value.

        Raises:
            ValueError: If environment name is not recognized.
        """
        normalized = value.lower().strip()

        # Handle common aliases
        aliases = {
            "dev": cls.DEVELOPMENT,
            "develop": cls.DEVELOPMENT,
            "development": cls.DEVELOPMENT,
            "local": cls.DEVELOPMENT,
            "stage": cls.STAGING,
            "staging": cls.STAGING,
            "qa": cls.STAGING,
            "prod": cls.PRODUCTION,
            "production": cls.PRODUCTION,
            "live": cls.PRODUCTION,
            "test": cls.TEST,
            "testing": cls.TEST,
            "ci": cls.TEST,
        }

        if normalized in aliases:
            return aliases[normalized]

        raise ValueError(
            f"Unknown environment: {value}. "
            f"Valid values: {', '.join(aliases.keys())}"
        )


def detect_environment() -> Environment:
    """Detect the current environment from environment variables.

    Checks the following environment variables in order:
    1. NEWSDIGEST_ENV
    2. APP_ENV
    3. ENVIRONMENT
    4. ENV

    Returns:
        Detected Environment, defaults to DEVELOPMENT if not set.
    """
    env_vars = ["NEWSDIGEST_ENV", "APP_ENV", "ENVIRONMENT", "ENV"]

    for var in env_vars:
        value = os.environ.get(var)
        if value:
            try:
                return Environment.from_string(value)
            except ValueError:
                continue

    # Default to development
    return Environment.DEVELOPMENT


def get_config_path(env: Environment | None = None) -> Path:
    """Get the path to the environment-specific configuration file.

    Args:
        env: Target environment. If None, auto-detects.

    Returns:
        Path to the configuration YAML file.
    """
    if env is None:
        env = detect_environment()

    # Look in multiple locations
    search_paths = [
        # Project config directory
        Path(__file__).parent.parent.parent.parent.parent
        / "config"
        / "environments"
        / f"{env.value}.yml",
        # Package config directory
        Path(__file__).parent.parent / "config" / f"{env.value}.yml",
        # Current working directory
        Path.cwd() / "config" / "environments" / f"{env.value}.yml",
        Path.cwd() / f".newsdigest.{env.value}.yml",
    ]

    for path in search_paths:
        if path.exists():
            return path

    # Return default path even if it doesn't exist
    return search_paths[0]


def get_env_file_path(env: Environment | None = None) -> Path:
    """Get the path to the environment-specific .env file.

    Args:
        env: Target environment. If None, auto-detects.

    Returns:
        Path to the .env file.
    """
    if env is None:
        env = detect_environment()

    # Look in multiple locations
    search_paths = [
        # Project config directory
        Path(__file__).parent.parent.parent.parent.parent
        / "config"
        / "environments"
        / f".env.{env.value}",
        # Current working directory
        Path.cwd() / f".env.{env.value}",
        Path.cwd() / ".env",
    ]

    for path in search_paths:
        if path.exists():
            return path

    return search_paths[0]


def load_env_file(path: Path | str | None = None) -> dict[str, str]:
    """Load environment variables from a .env file.

    Args:
        path: Path to .env file. If None, auto-detects based on environment.

    Returns:
        Dictionary of environment variables.
    """
    if path is None:
        path = get_env_file_path()
    else:
        path = Path(path)

    if not path.exists():
        return {}

    env_vars: dict[str, str] = {}

    with open(path) as f:
        for line in f:
            line = line.strip()

            # Skip empty lines and comments
            if not line or line.startswith("#"):
                continue

            # Parse key=value
            if "=" in line:
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip()

                # Remove surrounding quotes
                if value and value[0] in ('"', "'") and value[-1] == value[0]:
                    value = value[1:-1]

                env_vars[key] = value

    return env_vars


def apply_env_file(path: Path | str | None = None) -> None:
    """Load and apply environment variables from a .env file.

    Only sets variables that are not already defined in the environment.

    Args:
        path: Path to .env file. If None, auto-detects based on environment.
    """
    env_vars = load_env_file(path)

    for key, value in env_vars.items():
        if key not in os.environ:
            os.environ[key] = value


def load_config(env: Environment | None = None) -> Config:
    """Load configuration for the specified environment.

    This function:
    1. Detects the environment if not specified
    2. Loads the environment-specific .env file
    3. Loads the environment-specific YAML config
    4. Overrides with environment variables

    Args:
        env: Target environment. If None, auto-detects.

    Returns:
        Configured Config instance.
    """
    if env is None:
        env = detect_environment()

    # Apply environment-specific .env file
    apply_env_file(get_env_file_path(env))

    # Try to load YAML config
    config_path = get_config_path(env)

    # Missing file means defaults; set environment variables win either way
    return Config.load(config_path)


def get_environment_info() -> dict[str, Any]:
    """Get information about the current environment configuration.

    Returns:
        Dictionary with environment details.
    """
    env = detect_environment()

    return {
        "environment": env.value,
        "config_path": str(get_config_path(env)),
        "config_exists": get_config_path(env).exists(),
        "env_file_path": str(get_env_file_path(env)),
        "env_file_exists": get_env_file_path(env).exists(),
        "is_development": env == Environment.DEVELOPMENT,
        "is_staging": env == Environment.STAGING,
        "is_production": env == Environment.PRODUCTION,
        "is_test": env == Environment.TEST,
    }


# Convenience exports
def is_development() -> bool:
    """Check if running in development environment."""
    return detect_environment() == Environment.DEVELOPMENT


def is_staging() -> bool:
    """Check if running in staging environment."""
    return detect_environment() == Environment.STAGING


def is_production() -> bool:
    """Check if running in production environment."""
    return detect_environment() == Environment.PRODUCTION


def is_test() -> bool:
    """Check if running in test environment."""
    return detect_environment() == Environment.TEST
