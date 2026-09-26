"""Compare endpoint for NewsDigest API."""

import time

from fastapi import APIRouter, Request

from newsdigest.api.models import (
    CompareRequest,
    CompareResponse,
    DiffItem,
    Statistics,
)
from newsdigest.api.utils import get_config
from newsdigest.core.extractor import Extractor


router = APIRouter()


@router.post("/compare", response_model=CompareResponse)
async def compare_content(
    body: CompareRequest,
    request: Request,
) -> CompareResponse:
    """Compare original vs compressed content.

    Args:
        body: Compare request with source.
        request: FastAPI request object.

    Returns:
        Comparison showing what was kept and removed.
    """
    config = get_config(request)
    extractor = Extractor(config, mode=body.mode.value)

    start_time = time.perf_counter()

    # extract() handles URLs, RSS feeds and raw text
    result = await extractor.extract(body.source.strip())

    processing_time = (time.perf_counter() - start_time) * 1000

    # Build diff from sentences
    diff: list[DiffItem] = []
    for sentence in result.sentences:
        if sentence.keep:
            diff.append(
                DiffItem(
                    type="kept",
                    text=sentence.text,
                    reason=None,
                )
            )
        else:
            diff.append(
                DiffItem(
                    type="removed",
                    text=sentence.text,
                    reason=sentence.removal_reason,
                )
            )

    # Build removal breakdown
    breakdown: dict[str, int] = {}
    for r in result.removed:
        reason = r.reason.value.lower()
        breakdown[reason] = breakdown.get(reason, 0) + 1

    stats = Statistics(
        original_words=result.statistics.original_words,
        compressed_words=result.statistics.compressed_words,
        compression_ratio=result.statistics.compression_ratio,
        sentences_kept=sum(1 for s in result.sentences if s.keep),
        sentences_removed=sum(1 for s in result.sentences if not s.keep),
        processing_time_ms=processing_time,
        removal_breakdown=breakdown,
    )

    return CompareResponse(
        original=result.original_text or "",
        compressed=result.text,
        diff=diff,
        statistics=stats,
    )
