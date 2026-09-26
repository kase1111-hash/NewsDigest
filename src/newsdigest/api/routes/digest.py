"""Digest generation endpoint for NewsDigest API."""

from datetime import UTC, datetime

from fastapi import APIRouter, Request

from newsdigest.api.models import (
    DigestArticle,
    DigestContent,
    DigestRequest,
    DigestResponse,
    DigestSection,
    DigestStatistics,
    SourceType,
)
from newsdigest.api.utils import get_config
from newsdigest.digest.generator import Digest, DigestGenerator


router = APIRouter()


@router.post("/digest", response_model=DigestResponse)
async def generate_digest(
    body: DigestRequest,
    request: Request,
) -> DigestResponse:
    """Generate a news digest from multiple sources.

    Args:
        body: Digest request with sources and options.
        request: FastAPI request object.

    Returns:
        Digest response with generated content.
    """
    config = get_config(request)
    generator = DigestGenerator(
        config=config,
        mode=body.mode.value,
        max_items_per_source=body.max_articles,
        similarity_threshold=body.cluster_threshold,
    )

    # Add sources to generator
    for source in body.sources:
        if source.type == SourceType.RSS:
            generator.add_rss(url=source.url, name=source.name)
        elif source.type == SourceType.URL:
            generator.add_url(url=source.url, name=source.name)
        # NewsAPI would require additional setup

    # Generate digest
    digest_obj = await generator.generate_async(
        period="24h",
        format="dict",
    )
    if not isinstance(digest_obj, Digest):
        raise TypeError(f"Expected Digest from generator, got {type(digest_obj)}")

    # Convert to API response
    sections = []
    for topic in digest_obj.topics:
        articles = [
            DigestArticle(
                title=item.summary[:100] if item.summary else "Untitled",
                source=item.sources[0] if item.sources else "Unknown",
                summary=item.summary,
                url=item.urls[0] if item.urls else None,
            )
            for item in topic.items
        ]
        sections.append(
            DigestSection(
                topic=topic.name,
                articles=articles,
            )
        )

    # Calculate compression
    total_orig = digest_obj.total_original_words
    total_comp = digest_obj.total_compressed_words
    compression = 1 - (total_comp / total_orig) if total_orig > 0 else 0

    statistics = DigestStatistics(
        total_articles=digest_obj.articles_analyzed,
        articles_included=digest_obj.articles_analyzed,
        clusters=len(digest_obj.topics),
        total_original_words=total_orig,
        total_compressed_words=total_comp,
        overall_compression=compression,
    )

    # Build formatted content based on format
    content_lines = []
    for section in sections:
        content_lines.append(f"## {section.topic}")
        for article in section.articles:
            content_lines.append(f"- **{article.title}** ({article.source})")
            content_lines.append(f"  {article.summary[:200]}...")
        content_lines.append("")

    digest_content = DigestContent(
        title=f"News Digest - {datetime.now(UTC).strftime('%Y-%m-%d')}",
        generated_at=datetime.now(UTC),
        content="\n".join(content_lines),
        sections=sections,
        statistics=statistics,
    )

    return DigestResponse(success=True, digest=digest_content)
