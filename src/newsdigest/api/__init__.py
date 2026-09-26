"""REST API for NewsDigest."""

from newsdigest.api.app import app, create_app
from newsdigest.api.utils import get_config


__all__ = [
    "app",
    "create_app",
    "get_config",
]
