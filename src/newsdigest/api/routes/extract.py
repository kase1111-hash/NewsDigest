"""Extraction endpoints for NewsDigest API."""

import asyncio
import logging
import time

from fastapi import APIRouter, Request

from newsdigest.api.models import (
    BatchExtractionRequest,
    BatchExtractionResponse,
    BatchResultItem,
    BatchSummary,
    Claim,
    ExtractionRequest,
    ExtractionResponse,
    ExtractionResult,
    RemovedContent,
    Sentence,
    Statistics,
)
from newsdigest.api.utils import get_config
from newsdigest.core.extractor import Extractor
from newsdigest.core.result import ExtractionResult as CoreExtractionResult


logger = logging.getLogger(__name__)

router = APIRouter()


def _result_to_api(
    result: CoreExtractionResult,
    processing_time_ms: float,
) -> ExtractionResult:
    """Convert internal ExtractionResult to API model.

    Args:
        result: Internal extraction result.
        processing_time_ms: Processing time in milliseconds.

    Returns:
        API extraction result model.
    """
    # Convert sentences
    sentences = [
        Sentence(
            text=s.text,
            kept=s.keep,
            density_score=s.density_score,
            has_hedge=s.speculation_score > 0.3,
            has_speculation=s.speculation_score > 0.5,
            has_emotion=s.emotional_score > 0.5,
        )
        for s in result.sentences
    ]

    # Convert claims
    claims = [
        Claim(
            text=c.text,
            type=c.claim_type.value,
            confidence=c.confidence,
            source_attribution=c.source,
        )
        for c in result.claims
    ]

    # Convert removed content
    removed = [
        RemovedContent(
            text=r.text,
            reason=r.reason.value.lower(),
        )
        for r in result.removed
    ]

    # Build removal breakdown
    breakdown: dict[str, int] = {}
    for r in result.removed:
        reason = r.reason.value.lower()
        breakdown[reason] = breakdown.get(reason, 0) + 1

    # Build statistics
    stats = Statistics(
        original_words=result.statistics.original_words,
        compressed_words=result.statistics.compressed_words,
        compression_ratio=result.statistics.compression_ratio,
        sentences_kept=sum(1 for s in result.sentences if s.keep),
        sentences_removed=sum(1 for s in result.sentences if not s.keep),
        processing_time_ms=processing_time_ms,
        removal_breakdown=breakdown,
    )

    return ExtractionResult(
        title=result.title,
        source_url=result.url,
        publish_date=result.published_at,
        content=result.text,
        sentences=sentences,
        claims=claims,
        statistics=stats,
        removed_content=removed,
    )


@router.post("/extract", response_model=ExtractionResponse)
async def extract_content(
    body: ExtractionRequest,
    request: Request,
) -> ExtractionResponse:
    """Extract and compress content from a source.

    Args:
        body: Extraction request with source and options.
        request: FastAPI request object.

    Returns:
        Extraction response with results.
    """
    config = get_config(request)
    extractor = Extractor(config, mode=body.mode.value)

    start_time = time.perf_counter()

    # extract() handles URLs, RSS feeds and raw text
    result = await extractor.extract(body.source.strip())

    processing_time = (time.perf_counter() - start_time) * 1000

    api_result = _result_to_api(result, processing_time)

    return ExtractionResponse(success=True, result=api_result)


@router.post("/extract/batch", response_model=BatchExtractionResponse)
async def extract_batch(
    body: BatchExtractionRequest,
    request: Request,
) -> BatchExtractionResponse:
    """Extract content from multiple sources.

    Args:
        body: Batch extraction request.
        request: FastAPI request object.

    Returns:
        Batch extraction response with results for each source.
    """
    config = get_config(request)
    extractor = Extractor(config, mode=body.mode.value)

    results: list[BatchResultItem] = []
    succeeded = 0
    failed = 0

    # Create semaphore for concurrency control
    semaphore = asyncio.Semaphore(body.max_concurrent)

    async def extract_one(source: str) -> BatchResultItem:
        """Extract a single source with semaphore."""
        async with semaphore:
            start_time = time.perf_counter()
            try:
                result = await extractor.extract(source.strip())

                processing_time = (time.perf_counter() - start_time) * 1000
                api_result = _result_to_api(result, processing_time)

                return BatchResultItem(
                    source=source,
                    success=True,
                    result=api_result,
                )
            except Exception as e:
                # Log the full exception for debugging
                logger.exception("Batch extraction failed for source %s", source)
                return BatchResultItem(
                    source=source,
                    success=False,
                    error=str(e),
                )

    # Run extractions concurrently
    tasks = [extract_one(source) for source in body.sources]
    batch_results = await asyncio.gather(*tasks)

    for item in batch_results:
        results.append(item)
        if item.success:
            succeeded += 1
        else:
            failed += 1

    return BatchExtractionResponse(
        success=(failed == 0),
        results=results,
        summary=BatchSummary(
            total=len(body.sources),
            succeeded=succeeded,
            failed=failed,
        ),
    )
