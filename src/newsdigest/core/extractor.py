"""Main extraction engine for NewsDigest."""

import asyncio
import re
from urllib.parse import urlparse

from newsdigest.config.settings import Config
from newsdigest.core.article import Article
from newsdigest.core.pipeline import AnalysisPipeline
from newsdigest.core.result import (
    Claim,
    ExtractionResult,
    ExtractionStatistics,
    RemovalReason,
    RemovedContent,
    Sentence,
)
from newsdigest.exceptions import (
    ExtractionError,
    IngestError,
)
from newsdigest.formatters import JSONFormatter, MarkdownFormatter, TextFormatter
from newsdigest.ingestors import RSSParser, TextIngestor, URLFetcher
from newsdigest.parsers import ArticleExtractor
from newsdigest.utils.errors import ErrorSeverity, add_breadcrumb, capture_exception
from newsdigest.utils.logging import (
    get_logger,
    log_extraction_complete,
    log_extraction_start,
)


# Module logger
logger = get_logger(__name__)


class Extractor:
    """Main extraction engine that orchestrates the extraction pipeline.

    The Extractor:
    1. Ingests content from various sources (URL, RSS, text)
    2. Parses and cleans HTML
    3. Runs content through NLP pipeline
    4. Applies semantic analyzers
    5. Produces compressed output with statistics
    """

    def __init__(
        self,
        config: Config | None = None,
        mode: str = "standard",
    ) -> None:
        """Initialize extractor with configuration.

        Args:
            config: Configuration object. Uses defaults if not provided.
            mode: Extraction mode - 'conservative', 'standard', or 'aggressive'.
        """
        self.config = config or Config()
        self.mode = mode

        # Build config dict for components
        self._config_dict = self._build_config_dict()

        # Initialize components
        self._url_fetcher = URLFetcher(self._config_dict)
        self._rss_parser = RSSParser(self._config_dict)
        self._text_ingestor = TextIngestor(self._config_dict)
        self._article_extractor = ArticleExtractor(self._config_dict)
        self._pipeline = AnalysisPipeline(self._config_dict)

        # Initialize formatters
        self._formatters = {
            "markdown": MarkdownFormatter(self._config_dict.get("output", {})),
            "json": JSONFormatter(self._config_dict.get("output", {})),
            "text": TextFormatter(self._config_dict.get("output", {})),
        }

    def _build_config_dict(self) -> dict:
        """Build configuration dictionary from Config object."""
        config_dict = {
            "extraction": {
                "mode": self.mode,
                "speculation": self.config.extraction.speculation,
                "emotional_language": self.config.extraction.emotional_language,
                "unnamed_sources": self.config.extraction.unnamed_sources,
                "max_hedges_per_sentence": self.config.extraction.max_hedges_per_sentence,
                "min_sentence_density": self.config.extraction.min_sentence_density,
                "quotes": {
                    "keep_attributed": self.config.extraction.quotes.keep_attributed,
                    "keep_unattributed": self.config.extraction.quotes.keep_unattributed,
                    "flag_circular": self.config.extraction.quotes.flag_circular,
                },
            },
            "output": {
                "show_stats": self.config.output.show_stats,
                "include_links": self.config.output.include_links,
                "show_warnings": self.config.output.show_warnings,
            },
            "spacy_model": self.config.spacy_model,
            "timeout": self.config.http_timeout,
            "retries": self.config.http_retries,
            "requests_per_second": self.config.requests_per_second,
            "similarity_threshold": self.config.digest.similarity_threshold,
            "min_novelty_score": self.config.digest.min_novelty_score,
        }
        return config_dict

    async def extract(self, source: str) -> ExtractionResult:
        """Extract content from a single source.

        Args:
            source: URL string or raw text content.

        Returns:
            ExtractionResult with compressed content and statistics.

        Raises:
            IngestError: If content cannot be fetched or parsed.
            ExtractionError: If content cannot be processed.
            PipelineError: If NLP pipeline fails.
        """
        # Determine source type for logging
        source_type = "url" if self._is_url(source) else "text"
        log_extraction_start(logger, source, source_type)
        add_breadcrumb(
            f"Starting extraction from {source_type}",
            category="extraction",
            data={"source": source[:100] if source else None},
        )

        try:
            # Determine source type and ingest
            article = await self._ingest_source(source)
            logger.debug(f"Ingested article: {article.id}, {article.word_count} words")
            add_breadcrumb(
                f"Ingested article: {article.id}",
                category="extraction",
                data={"word_count": article.word_count},
            )
        except Exception as e:
            logger.error(f"Failed to ingest source: {e}", exc_info=True)
            capture_exception(
                e,
                severity=ErrorSeverity.ERROR,
                extra={"source": source[:100] if source else None, "source_type": source_type},
                tags={"operation": "ingest"},
            )
            if isinstance(e, IngestError):
                raise
            raise IngestError(
                f"Failed to ingest source: {e}",
                cause=e,
                details={"source": source[:100] if source else None},
            )

        try:
            # Process through pipeline
            result = self._process_article(article)

            # Log completion
            log_extraction_complete(
                logger,
                source,
                result.statistics.original_words,
                result.statistics.compressed_words,
                len(result.claims),
            )
            add_breadcrumb(
                "Extraction complete",
                category="extraction",
                data={
                    "compression": f"{result.statistics.compression_ratio:.1%}",
                    "claims": len(result.claims),
                },
            )

            return result
        except Exception as e:
            logger.error(f"Failed to extract content: {e}", exc_info=True)
            capture_exception(
                e,
                severity=ErrorSeverity.ERROR,
                extra={"article_id": article.id, "source": source[:100] if source else None},
                tags={"operation": "extraction"},
            )
            if isinstance(e, ExtractionError):
                raise
            raise ExtractionError(
                f"Failed to extract content: {e}",
                cause=e,
                details={"article_id": article.id},
            )

    def extract_sync(self, source: str) -> ExtractionResult:
        """Synchronous version of extract.

        Args:
            source: URL string or raw text content.

        Returns:
            ExtractionResult with compressed content and statistics.

        Raises:
            IngestError: If content cannot be fetched or parsed.
            ExtractionError: If content cannot be processed.
        """
        return asyncio.run(self.extract(source))

    async def extract_batch(
        self,
        sources: list[str],
        parallel: bool = True,
        max_workers: int = 5,
        fail_fast: bool = False,
    ) -> list[ExtractionResult]:
        """Extract content from multiple sources.

        Args:
            sources: List of URLs or text content.
            parallel: Whether to process in parallel.
            max_workers: Maximum concurrent workers.
            fail_fast: If True, raise on first error. Otherwise, skip failures.

        Returns:
            List of ExtractionResult objects (failed extractions excluded unless fail_fast).

        Raises:
            ExtractionError: If fail_fast is True and any extraction fails.
        """
        if parallel:
            semaphore = asyncio.Semaphore(max_workers)

            async def extract_one(src: str) -> ExtractionResult | None:
                async with semaphore:
                    try:
                        return await self.extract(src)
                    except Exception as e:
                        capture_exception(
                            e,
                            severity=ErrorSeverity.WARNING if not fail_fast else ErrorSeverity.ERROR,
                            extra={"source": src[:100] if src else None},
                            tags={"operation": "batch_extraction"},
                        )
                        if fail_fast:
                            raise ExtractionError(
                                f"Batch extraction failed: {e}",
                                cause=e,
                                details={"source": src[:100] if src else None},
                            )
                        return None

            tasks = [extract_one(src) for src in sources]
            results = await asyncio.gather(*tasks, return_exceptions=not fail_fast)
            return [r for r in results if r is not None and not isinstance(r, Exception)]
        else:
            results = []
            for src in sources:
                try:
                    result = await self.extract(src)
                    results.append(result)
                except Exception as e:
                    capture_exception(
                        e,
                        severity=ErrorSeverity.WARNING if not fail_fast else ErrorSeverity.ERROR,
                        extra={"source": src[:100] if src else None},
                        tags={"operation": "batch_extraction"},
                    )
                    if fail_fast:
                        raise ExtractionError(
                            f"Batch extraction failed: {e}",
                            cause=e,
                            details={"source": src[:100] if src else None},
                        )
                    continue
            return results

    def compare(self, source: str) -> ExtractionResult:
        """Generate side-by-side comparison view.

        Returns original text with annotations alongside extracted version.

        Args:
            source: URL or text content.

        Returns:
            ExtractionResult with original_text and sentence annotations.
        """
        result = self.extract_sync(source)
        # The result already contains sentences with keep/removal info
        # Just ensure original_text is populated
        return result

    def extract_text(self, text: str) -> ExtractionResult:
        """Extract content from plain text input.

        Synchronous method for processing raw text content directly.

        Args:
            text: Plain text content to process.

        Returns:
            ExtractionResult with compressed content and statistics.

        Raises:
            ExtractionError: If content cannot be processed.
        """
        return self.extract_sync(text)

    async def _ingest_source(self, source: str) -> Article:
        """Determine source type and ingest content.

        Args:
            source: URL, RSS feed URL, or text content.

        Returns:
            Article object.
        """
        source = source.strip()

        # Check if it's a URL
        if self._is_url(source):
            # Check if RSS feed
            if self._looks_like_rss(source):
                articles = await self._rss_parser.parse(source, limit=1)
                if articles:
                    return articles[0]

            # Regular URL
            return await self._url_fetcher.ingest(source)

        # Plain text
        return self._text_ingestor.from_text(source)

    def _is_url(self, source: str) -> bool:
        """Check if source is a URL.

        Args:
            source: Source string.

        Returns:
            True if URL.
        """
        # TODO: urlparse is permissive — consider stricter URL validation
        # (e.g. the validation module's validate_url) for untrusted input
        try:
            result = urlparse(source)
            return all([result.scheme in ("http", "https"), result.netloc])
        except (ValueError, AttributeError):
            return False

    def _looks_like_rss(self, url: str) -> bool:
        """Check if URL looks like an RSS feed.

        Args:
            url: URL to check.

        Returns:
            True if likely RSS.
        """
        rss_indicators = [
            "/feed",
            "/rss",
            "/atom",
            ".xml",
            ".rss",
            "feed=",
            "format=rss",
        ]
        url_lower = url.lower()
        return any(ind in url_lower for ind in rss_indicators)

    def _process_article(self, article: Article) -> ExtractionResult:
        """Process article through analysis pipeline.

        Args:
            article: Article to process.

        Returns:
            ExtractionResult.
        """
        # Process through NLP pipeline
        sentences = self._pipeline.process_and_analyze(article.content)

        # Get claims from pipeline
        claims = self._pipeline.get_claims()

        # Build extracted text from kept sentences
        kept_sentences = [s for s in sentences if s.keep]
        extracted_text = " ".join(s.text for s in kept_sentences)

        # Build removed content list
        removed_content = self._build_removed_list(sentences)

        # Get source warnings
        warnings = self._build_warnings(sentences)

        # Get named sources
        sources_named = self._get_named_sources(sentences)

        # Calculate statistics
        statistics = self._calculate_statistics(
            article, sentences, kept_sentences, claims
        )

        return ExtractionResult(
            id=article.id,
            url=article.url,
            title=article.title,
            source=article.source_name,
            published_at=article.published_at,
            text=extracted_text,
            claims=claims,
            sources_named=sources_named,
            warnings=warnings,
            removed=removed_content,
            statistics=statistics,
            original_text=article.content,
            sentences=sentences,
        )

    def _build_removed_list(self, sentences: list[Sentence]) -> list[RemovedContent]:
        """Build list of removed content.

        Args:
            sentences: Analyzed sentences.

        Returns:
            List of RemovedContent objects.
        """
        removed = []
        for sentence in sentences:
            if not sentence.keep and sentence.removal_reason:
                try:
                    reason = RemovalReason(sentence.removal_reason)
                except ValueError:
                    reason = RemovalReason.LOW_DENSITY

                removed.append(
                    RemovedContent(
                        text=sentence.text,
                        reason=reason,
                        sentence_index=sentence.index,
                        original_length=len(sentence.text.split()),
                    )
                )
        return removed

    def _build_warnings(self, sentences: list[Sentence]) -> list[dict]:
        """Build warnings list from sentences.

        Args:
            sentences: Analyzed sentences.

        Returns:
            List of warning dictionaries.
        """
        warnings = []
        for sentence in sentences:
            if sentence.has_unnamed_source and sentence.keep:
                warnings.append(
                    {
                        "type": "UNNAMED_SOURCE",
                        "text": sentence.text[:100] + "..."
                        if len(sentence.text) > 100
                        else sentence.text,
                        "location": f"sentence {sentence.index + 1}",
                    }
                )
        return warnings

    def _get_named_sources(self, sentences: list[Sentence]) -> list[str]:
        """Get list of named sources from sentences.

        Args:
            sentences: Analyzed sentences.

        Returns:
            List of unique source names.
        """
        sources = set()
        for sentence in sentences:
            if sentence.source_name:
                sources.add(sentence.source_name)
        return list(sources)

    def _calculate_statistics(
        self,
        article: Article,
        all_sentences: list[Sentence],
        kept_sentences: list[Sentence],
        claims: list[Claim],
    ) -> ExtractionStatistics:
        """Calculate extraction statistics.

        Args:
            article: Original article.
            all_sentences: All analyzed sentences.
            kept_sentences: Sentences that were kept.
            claims: Extracted claims.

        Returns:
            ExtractionStatistics object.
        """
        original_words = article.word_count
        compressed_words = sum(len(s.text.split()) for s in kept_sentences)

        # Calculate compression ratio
        compression_ratio = (
            1 - compressed_words / original_words if original_words > 0 else 0
        )

        # Calculate densities
        original_density = self._calculate_density(article.content, [])
        compressed_density = self._calculate_density(
            " ".join(s.text for s in kept_sentences), claims
        )

        # Count by removal reason
        speculation_removed = sum(
            1
            for s in all_sentences
            if not s.keep and s.removal_reason == RemovalReason.SPECULATION.value
        )
        background_removed = sum(
            1
            for s in all_sentences
            if not s.keep and s.removal_reason == RemovalReason.BACKGROUND_REPEAT.value
        )
        repetition_collapsed = background_removed  # Same thing

        # Count sources
        named_sources = sum(1 for s in all_sentences if s.has_named_source)
        unnamed_sources = sum(1 for s in all_sentences if s.has_unnamed_source)

        # Count emotional words (from pipeline stats)
        pipeline_stats = self._pipeline.get_statistics(all_sentences)
        emotional_words = pipeline_stats.get("emotional_words_removed", 0)

        return ExtractionStatistics(
            original_words=original_words,
            compressed_words=compressed_words,
            compression_ratio=round(compression_ratio, 3),
            original_density=round(original_density, 2),
            compressed_density=round(compressed_density, 2),
            novel_claims=len(claims),
            background_removed=background_removed,
            speculation_removed=speculation_removed,
            repetition_collapsed=repetition_collapsed,
            emotional_words_removed=emotional_words,
            unnamed_sources=unnamed_sources,
            named_sources=named_sources,
        )

    def _calculate_density(self, text: str, claims: list[Claim]) -> float:
        """Calculate semantic density score.

        Args:
            text: Text content.
            claims: Claims extracted from text.

        Returns:
            Density score 0.0-1.0.
        """
        word_count = len(text.split())
        if word_count == 0:
            return 0.0

        claim_count = len(claims)
        if claim_count == 0:
            # FIXME: Entity-based density estimation is a rough heuristic;
            # consider using sentence-transformers for semantic density scoring
            entity_pattern = r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b'
            entities = re.findall(entity_pattern, text)
            claim_count = len(set(entities)) // 3  # Rough estimate

        avg_confidence = (
            sum(c.confidence for c in claims) / claim_count if claim_count > 0 else 0.5
        )

        raw_density = (claim_count * avg_confidence) / word_count
        scaling_factor = 10.0
        density = min(1.0, raw_density * scaling_factor)

        return round(density, 2)

    def format(
        self,
        result: ExtractionResult,
        format: str = "markdown",
    ) -> str:
        """Format extraction result.

        Args:
            result: ExtractionResult to format.
            format: Output format (markdown, json, text).

        Returns:
            Formatted string.
        """
        formatter = self._formatters.get(format.lower())
        if not formatter:
            raise ValueError(f"Unknown format: {format}")
        return formatter.format_result(result)

    def format_stats(
        self,
        result: ExtractionResult,
        format: str = "text",
    ) -> str:
        """Format statistics only.

        Args:
            result: ExtractionResult.
            format: Output format.

        Returns:
            Formatted statistics string.
        """
        formatter = self._formatters.get(format.lower())
        if not formatter:
            raise ValueError(f"Unknown format: {format}")
        return formatter.format_stats(result)

    def format_comparison(
        self,
        result: ExtractionResult,
        format: str = "markdown",
    ) -> str:
        """Format comparison view.

        Args:
            result: ExtractionResult with sentences.
            format: Output format.

        Returns:
            Formatted comparison string.
        """
        formatter = self._formatters.get(format.lower())
        if not formatter:
            raise ValueError(f"Unknown format: {format}")
        return formatter.format_comparison(result)
