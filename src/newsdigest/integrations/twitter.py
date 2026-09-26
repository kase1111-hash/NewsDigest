"""Twitter/X integration for NewsDigest.

Fetches tweets and threads from Twitter/X for analysis.
Requires: pip install newsdigest[twitter]
"""

import contextlib
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import httpx


try:
    import tweepy

    HAS_TWEEPY = True
except ImportError:
    HAS_TWEEPY = False
    tweepy = None  # type: ignore


@dataclass
class Tweet:
    """A tweet from Twitter/X."""

    id: str
    text: str
    author_id: str
    author_username: str | None = None
    author_name: str | None = None
    created_at: datetime | None = None
    retweet_count: int = 0
    like_count: int = 0
    reply_count: int = 0
    quote_count: int = 0
    url: str | None = None
    is_retweet: bool = False
    is_reply: bool = False
    conversation_id: str | None = None
    in_reply_to_user_id: str | None = None
    entities: dict[str, Any] = field(default_factory=dict)


@dataclass
class TwitterConfig:
    """Twitter API configuration.

    For API v2 access, you need a Bearer Token from the Twitter Developer Portal.
    """

    bearer_token: str
    # OAuth 1.0a for user context (optional)
    api_key: str | None = None
    api_secret: str | None = None
    access_token: str | None = None
    access_token_secret: str | None = None


class TwitterClient:
    """Client for fetching content from Twitter/X.

    Uses Twitter API v2 for fetching tweets and user data.

    Example:
        >>> client = TwitterClient(bearer_token="your-token")
        >>> tweets = await client.search_recent("breaking news")
        >>> tweets = await client.get_user_tweets("elonmusk")
    """

    BASE_URL = "https://api.twitter.com/2"

    def __init__(
        self,
        config: TwitterConfig | None = None,
        bearer_token: str = "",
    ) -> None:
        """Initialize Twitter client.

        Args:
            config: Twitter API configuration.
            bearer_token: Bearer token (alternative to config).
        """
        if config:
            self.config = config
        else:
            self.config = TwitterConfig(bearer_token=bearer_token)

        if not self.config.bearer_token:
            raise ValueError(
                "Twitter Bearer Token is required. "
                "Get one at https://developer.twitter.com"
            )

        self._client = httpx.AsyncClient(
            headers={"Authorization": f"Bearer {self.config.bearer_token}"},
            timeout=30.0,
        )

    async def search_recent(
        self,
        query: str,
        max_results: int = 100,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> list[Tweet]:
        """Search recent tweets.

        Searches tweets from the last 7 days.

        Args:
            query: Search query (supports Twitter search operators).
            max_results: Maximum number of results (10-100).
            start_time: Oldest tweet timestamp.
            end_time: Newest tweet timestamp.

        Returns:
            List of matching tweets.
        """
        params: dict[str, Any] = {
            "query": query,
            "max_results": min(max_results, 100),
            "tweet.fields": "created_at,public_metrics,conversation_id,"
            "in_reply_to_user_id,entities,referenced_tweets",
            "expansions": "author_id",
            "user.fields": "username,name",
        }

        if start_time:
            params["start_time"] = start_time.isoformat()
        if end_time:
            params["end_time"] = end_time.isoformat()

        response = await self._client.get(
            f"{self.BASE_URL}/tweets/search/recent",
            params=params,
        )
        response.raise_for_status()

        data = response.json()
        return self._parse_tweets(data)

    async def get_user_tweets(
        self,
        username: str,
        max_results: int = 100,
        exclude_replies: bool = True,
        exclude_retweets: bool = True,
    ) -> list[Tweet]:
        """Get tweets from a specific user.

        Args:
            username: Twitter username (without @).
            max_results: Maximum number of results.
            exclude_replies: Exclude reply tweets.
            exclude_retweets: Exclude retweets.

        Returns:
            List of user's tweets.
        """
        # First, get user ID from username
        user_response = await self._client.get(
            f"{self.BASE_URL}/users/by/username/{username}",
        )
        user_response.raise_for_status()
        user_data = user_response.json()
        user_id = user_data.get("data", {}).get("id")

        if not user_id:
            return []

        # Build exclude list
        exclude = []
        if exclude_replies:
            exclude.append("replies")
        if exclude_retweets:
            exclude.append("retweets")

        params: dict[str, Any] = {
            "max_results": min(max_results, 100),
            "tweet.fields": "created_at,public_metrics,conversation_id,"
            "in_reply_to_user_id,entities,referenced_tweets",
        }

        if exclude:
            params["exclude"] = ",".join(exclude)

        response = await self._client.get(
            f"{self.BASE_URL}/users/{user_id}/tweets",
            params=params,
        )
        response.raise_for_status()

        data = response.json()
        tweets = self._parse_tweets(data)

        # Add username to all tweets
        for tweet in tweets:
            tweet.author_username = username

        return tweets

    async def get_thread(self, tweet_id: str) -> list[Tweet]:
        """Get a tweet thread/conversation.

        Args:
            tweet_id: ID of any tweet in the thread.

        Returns:
            List of tweets in the thread, ordered chronologically.
        """
        # Get the original tweet to find conversation ID
        response = await self._client.get(
            f"{self.BASE_URL}/tweets/{tweet_id}",
            params={
                "tweet.fields": "conversation_id,author_id",
                "expansions": "author_id",
                "user.fields": "username,name",
            },
        )
        response.raise_for_status()

        data = response.json()
        tweet_data = data.get("data", {})
        conversation_id = tweet_data.get("conversation_id")
        author_id = tweet_data.get("author_id")

        if not conversation_id or not author_id:
            return []

        # Search for all tweets in the conversation by this author
        query = f"conversation_id:{conversation_id} from:{author_id}"
        tweets = await self.search_recent(query, max_results=100)

        # Sort by creation time
        tweets.sort(key=lambda t: t.created_at or datetime.min)

        return tweets

    async def get_tweet(self, tweet_id: str) -> Tweet | None:
        """Get a single tweet by ID.

        Args:
            tweet_id: Tweet ID.

        Returns:
            Tweet object or None if not found.
        """
        response = await self._client.get(
            f"{self.BASE_URL}/tweets/{tweet_id}",
            params={
                "tweet.fields": "created_at,public_metrics,conversation_id,"
                "in_reply_to_user_id,entities,referenced_tweets",
                "expansions": "author_id",
                "user.fields": "username,name",
            },
        )

        if response.status_code == 404:
            return None

        response.raise_for_status()

        data = response.json()
        tweets = self._parse_tweets(data)
        return tweets[0] if tweets else None

    def _parse_tweets(self, data: dict[str, Any]) -> list[Tweet]:
        """Parse tweet data from API response.

        Args:
            data: Raw API response data.

        Returns:
            List of Tweet objects.
        """
        tweets_data = data.get("data", [])
        if isinstance(tweets_data, dict):
            tweets_data = [tweets_data]

        # Build user lookup from includes
        users: dict[str, dict[str, str]] = {}
        for user in data.get("includes", {}).get("users", []):
            users[user["id"]] = {
                "username": user.get("username", ""),
                "name": user.get("name", ""),
            }

        result = []
        for tweet in tweets_data:
            # Parse created_at
            created_str = tweet.get("created_at")
            created_at = None
            if created_str:
                with contextlib.suppress(ValueError):
                    created_at = datetime.fromisoformat(
                        created_str.replace("Z", "+00:00")
                    )

            # Get metrics
            metrics = tweet.get("public_metrics", {})

            # Check for retweet/reply
            referenced = tweet.get("referenced_tweets", [])
            is_retweet = any(r.get("type") == "retweeted" for r in referenced)
            is_reply = any(r.get("type") == "replied_to" for r in referenced)

            # Get author info
            author_id = tweet.get("author_id", "")
            author_info = users.get(author_id, {})

            tweet_id = tweet.get("id", "")
            result.append(
                Tweet(
                    id=tweet_id,
                    text=tweet.get("text", ""),
                    author_id=author_id,
                    author_username=author_info.get("username"),
                    author_name=author_info.get("name"),
                    created_at=created_at,
                    retweet_count=metrics.get("retweet_count", 0),
                    like_count=metrics.get("like_count", 0),
                    reply_count=metrics.get("reply_count", 0),
                    quote_count=metrics.get("quote_count", 0),
                    url=f"https://twitter.com/i/status/{tweet_id}",
                    is_retweet=is_retweet,
                    is_reply=is_reply,
                    conversation_id=tweet.get("conversation_id"),
                    in_reply_to_user_id=tweet.get("in_reply_to_user_id"),
                    entities=tweet.get("entities", {}),
                )
            )

        return result

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()

    async def __aenter__(self) -> "TwitterClient":
        """Async context manager entry."""
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Async context manager exit."""
        await self.close()


class TwitterIngestor:
    """Ingestor for Twitter content.

    Fetches tweets from configured sources for analysis.

    Example:
        >>> ingestor = TwitterIngestor(bearer_token="your-token")
        >>> ingestor.add_user("elonmusk")
        >>> ingestor.add_search("AI news", "#AI OR #MachineLearning")
        >>> tweets = await ingestor.fetch_all()
    """

    def __init__(
        self,
        bearer_token: str,
        config: TwitterConfig | None = None,
    ) -> None:
        """Initialize ingestor.

        Args:
            bearer_token: Twitter Bearer Token.
            config: Optional configuration.
        """
        self.config = config or TwitterConfig(bearer_token=bearer_token)
        self._client = TwitterClient(config=self.config)
        self._sources: list[dict[str, Any]] = []

    def add_user(self, username: str, name: str | None = None) -> None:
        """Add a user to fetch tweets from.

        Args:
            username: Twitter username (without @).
            name: Display name for the source.
        """
        self._sources.append(
            {
                "type": "user",
                "username": username,
                "name": name or f"@{username}",
            }
        )

    def add_search(self, name: str, query: str) -> None:
        """Add a search query.

        Args:
            name: Display name for the source.
            query: Twitter search query.
        """
        self._sources.append(
            {
                "type": "search",
                "name": name,
                "query": query,
            }
        )

    async def fetch_all(self, max_per_source: int = 50) -> list[dict[str, Any]]:
        """Fetch tweets from all configured sources.

        Args:
            max_per_source: Maximum tweets per source.

        Returns:
            List of tweet dictionaries ready for extraction.
        """
        all_tweets = []

        for source in self._sources:
            try:
                if source["type"] == "user":
                    tweets = await self._client.get_user_tweets(
                        source["username"],
                        max_results=max_per_source,
                    )
                else:
                    tweets = await self._client.search_recent(
                        source["query"],
                        max_results=max_per_source,
                    )

                all_tweets.extend(
                    {
                        "url": tweet.url,
                        "text": tweet.text,
                        "source_name": source["name"],
                        "author": tweet.author_username or tweet.author_id,
                        "published_at": tweet.created_at,
                        "metrics": {
                            "likes": tweet.like_count,
                            "retweets": tweet.retweet_count,
                            "replies": tweet.reply_count,
                        },
                    }
                    for tweet in tweets
                )

            except Exception:
                # Skip failed sources
                continue

        return all_tweets

    async def close(self) -> None:
        """Close the client."""
        await self._client.close()
