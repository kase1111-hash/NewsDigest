"""Pydantic models for NewsDigest API."""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ExtractionMode(str, Enum):
    """Extraction aggressiveness mode."""

    CONSERVATIVE = "conservative"
    STANDARD = "standard"
    AGGRESSIVE = "aggressive"


class OutputFormat(str, Enum):
    """Output format options."""

    JSON = "json"
    MARKDOWN = "markdown"
    TEXT = "text"


class HealthStatus(str, Enum):
    """Service health status."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


class SourceType(str, Enum):
    """Digest source type."""

    RSS = "rss"
    URL = "url"
    NEWSAPI = "newsapi"


# Request Models


class ExtractionRequest(BaseModel):
    """Request body for content extraction."""

    source: str = Field(
        ...,
        min_length=1,
        max_length=100000,
        description="URL, RSS feed URL, or raw text content",
    )
    mode: ExtractionMode = Field(
        default=ExtractionMode.STANDARD,
        description="Extraction aggressiveness",
    )
    format: OutputFormat = Field(
        default=OutputFormat.JSON,
        description="Output format",
    )


class BatchExtractionRequest(BaseModel):
    """Request body for batch extraction."""

    sources: list[str] = Field(
        ...,
        min_length=1,
        max_length=50,
        description="List of URLs or text content to extract",
    )
    mode: ExtractionMode = Field(default=ExtractionMode.STANDARD)
    format: OutputFormat = Field(default=OutputFormat.JSON)
    max_concurrent: int = Field(
        default=5,
        ge=1,
        le=10,
        description="Maximum concurrent extractions",
    )


class DigestSource(BaseModel):
    """A single source for digest generation."""

    type: SourceType
    url: str
    name: str | None = None


class DigestRequest(BaseModel):
    """Request body for digest generation."""

    sources: list[DigestSource] = Field(
        ...,
        min_length=1,
        max_length=20,
        description="News sources to include",
    )
    mode: ExtractionMode = Field(default=ExtractionMode.STANDARD)
    format: OutputFormat = Field(default=OutputFormat.MARKDOWN)
    max_articles: int = Field(
        default=20,
        ge=1,
        le=100,
        description="Maximum articles per source",
    )
    cluster_threshold: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="Similarity above which articles are merged as duplicates",
    )


class CompareRequest(BaseModel):
    """Request body for content comparison."""

    source: str = Field(
        ...,
        min_length=1,
        max_length=100000,
        description="URL or text to compare",
    )
    mode: ExtractionMode = Field(default=ExtractionMode.STANDARD)


# Response Models


class HealthResponse(BaseModel):
    """Health check response."""

    status: HealthStatus
    version: str
    timestamp: datetime


class Statistics(BaseModel):
    """Extraction statistics."""

    original_words: int = 0
    compressed_words: int = 0
    compression_ratio: float = 0.0
    sentences_kept: int = 0
    sentences_removed: int = 0
    processing_time_ms: float = 0.0
    removal_breakdown: dict[str, int] = Field(default_factory=dict)


class Claim(BaseModel):
    """An extracted claim."""

    text: str
    type: str
    confidence: float = 0.0
    source_attribution: str | None = None


class Sentence(BaseModel):
    """An analyzed sentence."""

    text: str
    kept: bool
    density_score: float = 0.0
    has_hedge: bool = False
    has_speculation: bool = False
    has_emotion: bool = False


class RemovedContent(BaseModel):
    """Content that was removed."""

    text: str
    reason: str


class ExtractionResult(BaseModel):
    """Result of content extraction."""

    title: str | None = None
    source_url: str | None = None
    author: str | None = None
    publish_date: datetime | None = None
    content: str = ""
    sentences: list[Sentence] = Field(default_factory=list)
    claims: list[Claim] = Field(default_factory=list)
    statistics: Statistics = Field(default_factory=Statistics)
    removed_content: list[RemovedContent] = Field(default_factory=list)


class ExtractionResponse(BaseModel):
    """Response for extraction endpoint."""

    success: bool
    result: ExtractionResult


class BatchResultItem(BaseModel):
    """Single result in batch extraction."""

    source: str
    success: bool
    result: ExtractionResult | None = None
    error: str | None = None


class BatchSummary(BaseModel):
    """Summary of batch extraction."""

    total: int
    succeeded: int
    failed: int


class BatchExtractionResponse(BaseModel):
    """Response for batch extraction endpoint."""

    success: bool
    results: list[BatchResultItem]
    summary: BatchSummary


class DigestArticle(BaseModel):
    """Article in a digest section."""

    title: str
    source: str
    summary: str
    url: str | None = None


class DigestSection(BaseModel):
    """A topic section in the digest."""

    topic: str
    articles: list[DigestArticle]


class DigestStatistics(BaseModel):
    """Statistics for digest generation."""

    total_articles: int = 0
    articles_included: int = 0
    clusters: int = 0
    total_original_words: int = 0
    total_compressed_words: int = 0
    overall_compression: float = 0.0


class DigestContent(BaseModel):
    """The generated digest."""

    title: str
    generated_at: datetime
    content: str
    sections: list[DigestSection]
    statistics: DigestStatistics


class DigestResponse(BaseModel):
    """Response for digest endpoint."""

    success: bool
    digest: DigestContent


class DiffItem(BaseModel):
    """A single item in the comparison diff."""

    type: str  # "kept" or "removed"
    text: str
    reason: str | None = None


class CompareResponse(BaseModel):
    """Response for compare endpoint."""

    original: str
    compressed: str
    diff: list[DiffItem]
    statistics: Statistics


class ErrorResponse(BaseModel):
    """Error response model."""

    error: str
    message: str
    details: dict[str, Any] | None = None
    request_id: str | None = None
