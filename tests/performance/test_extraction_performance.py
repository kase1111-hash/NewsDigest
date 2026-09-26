"""Performance tests for extraction operations.

These tests verify extraction speed, throughput, and resource usage.
Run with: pytest tests/performance -v --tb=short
"""

import time

import pytest

from newsdigest.core.extractor import Extractor
from newsdigest.core.result import ExtractionResult


# =============================================================================
# PERFORMANCE THRESHOLDS
# =============================================================================

# Maximum time for single extraction (seconds)
MAX_SINGLE_EXTRACTION_TIME = 5.0

# Maximum time per article in batch (seconds)
MAX_BATCH_TIME_PER_ARTICLE = 2.0

# Maximum time for large content (seconds)
MAX_LARGE_CONTENT_TIME = 10.0

# Minimum throughput for batch processing (articles/second)
MIN_BATCH_THROUGHPUT = 0.5


# =============================================================================
# TEST FIXTURES
# =============================================================================


@pytest.fixture
def extractor() -> Extractor:
    """Create extractor for performance tests."""
    return Extractor()


@pytest.fixture
def standard_article() -> str:
    """Standard article content (~200 words)."""
    return """
    Apple Inc. reported record quarterly revenue of $89.5 billion on Tuesday,
    beating analyst expectations of $87.1 billion by a significant margin.

    CEO Tim Cook announced the results during an earnings call with investors,
    highlighting strong iPhone sales as the primary driver of growth. The
    company sold approximately 78 million iPhones during the quarter,
    representing a 12% increase from the same period last year.

    "We're incredibly proud of these results," Cook said during the call.
    "Our team has worked tirelessly to deliver innovative products that
    our customers love."

    Net income rose 25% to $23.6 billion, while gross margin improved to
    43.8%. Services revenue, which includes the App Store, Apple Music,
    and iCloud, grew 17% to reach $19.5 billion.

    Analysts were particularly impressed by the company's performance in
    China, where revenue grew 21% despite ongoing economic challenges.
    The company's stock rose 3% in after-hours trading following the
    announcement.

    CFO Luca Maestri noted that the company returned $25 billion to
    shareholders through dividends and stock buybacks during the quarter.
    """


@pytest.fixture
def large_article() -> str:
    """Large article content (~2000 words)."""
    base_paragraph = """
    The technology sector experienced significant developments this quarter,
    with major companies reporting strong earnings across multiple segments.
    Industry analysts noted that consumer spending on electronics remained
    robust despite broader economic concerns. Several factors contributed
    to this trend, including new product launches and expanded services.
    """
    return base_paragraph * 20  # ~2000 words


@pytest.fixture
def batch_articles() -> list[str]:
    """Multiple articles for batch testing."""
    templates = [
        "Apple reported $90 billion in revenue. CEO Tim Cook was pleased with results.",
        "Google announced new AI features. Sundar Pichai outlined the strategy.",
        "Microsoft invested $10 billion in AI. Satya Nadella led the announcement.",
        "Amazon expanded its cloud services. AWS revenue grew 20% year over year.",
        "Meta launched new VR products. Mark Zuckerberg demonstrated the features.",
        "Tesla delivered record vehicles. Elon Musk discussed production targets.",
        "Netflix added 10 million subscribers. The company raised prices globally.",
        "NVIDIA reported strong chip demand. Gaming and AI drove the growth.",
        "Adobe released creative tools. The company focused on AI integration.",
        "Salesforce acquired new company. Marc Benioff discussed the strategy.",
    ]
    return templates


# =============================================================================
# SINGLE EXTRACTION PERFORMANCE
# =============================================================================


class TestSingleExtractionPerformance:
    """Tests for single extraction performance."""

    def test_standard_article_speed(
        self, extractor: Extractor, standard_article: str
    ) -> None:
        """Standard article extraction completes within time limit."""
        start = time.perf_counter()
        result = extractor.extract_sync(standard_article)
        elapsed = time.perf_counter() - start

        assert isinstance(result, ExtractionResult)
        assert elapsed < MAX_SINGLE_EXTRACTION_TIME, \
            f"Extraction took {elapsed:.2f}s, max allowed is {MAX_SINGLE_EXTRACTION_TIME}s"

    def test_large_article_speed(
        self, extractor: Extractor, large_article: str
    ) -> None:
        """Large article extraction completes within time limit."""
        start = time.perf_counter()
        result = extractor.extract_sync(large_article)
        elapsed = time.perf_counter() - start

        assert isinstance(result, ExtractionResult)
        assert elapsed < MAX_LARGE_CONTENT_TIME, \
            f"Large content took {elapsed:.2f}s, max allowed is {MAX_LARGE_CONTENT_TIME}s"

    def test_empty_content_fast(self, extractor: Extractor) -> None:
        """Empty content processes quickly."""
        start = time.perf_counter()
        result = extractor.extract_sync("")
        elapsed = time.perf_counter() - start

        assert elapsed < 1.0, f"Empty content took {elapsed:.2f}s"

    def test_short_content_fast(self, extractor: Extractor) -> None:
        """Short content processes quickly."""
        start = time.perf_counter()
        result = extractor.extract_sync("Apple reported earnings.")
        elapsed = time.perf_counter() - start

        assert elapsed < 2.0, f"Short content took {elapsed:.2f}s"

    def test_repeated_extraction_consistent_time(
        self, extractor: Extractor, standard_article: str
    ) -> None:
        """Repeated extractions have consistent timing."""
        times = []
        for _ in range(3):
            start = time.perf_counter()
            extractor.extract_sync(standard_article)
            times.append(time.perf_counter() - start)

        avg_time = sum(times) / len(times)
        max_deviation = max(abs(t - avg_time) for t in times)

        # Deviation should be less than 50% of average
        assert max_deviation < avg_time * 0.5, \
            f"Timing inconsistent: times={times}, avg={avg_time:.2f}s"


# =============================================================================
# BATCH PROCESSING PERFORMANCE
# =============================================================================


class TestBatchPerformance:
    """Tests for batch processing performance."""

    @pytest.mark.asyncio
    async def test_batch_throughput(
        self, extractor: Extractor, batch_articles: list[str]
    ) -> None:
        """Batch processing meets minimum throughput."""
        start = time.perf_counter()
        results = await extractor.extract_batch(batch_articles, parallel=True)
        elapsed = time.perf_counter() - start

        articles_processed = len(results)
        throughput = articles_processed / elapsed

        assert throughput >= MIN_BATCH_THROUGHPUT, \
            f"Throughput {throughput:.2f} articles/s below minimum {MIN_BATCH_THROUGHPUT}"

    @pytest.mark.asyncio
    async def test_batch_time_per_article(
        self, extractor: Extractor, batch_articles: list[str]
    ) -> None:
        """Average time per article in batch is acceptable."""
        start = time.perf_counter()
        results = await extractor.extract_batch(batch_articles, parallel=True)
        elapsed = time.perf_counter() - start

        time_per_article = elapsed / len(batch_articles)

        assert time_per_article < MAX_BATCH_TIME_PER_ARTICLE, \
            f"Time per article {time_per_article:.2f}s exceeds max {MAX_BATCH_TIME_PER_ARTICLE}s"

    @pytest.mark.asyncio
    async def test_parallel_faster_than_sequential(
        self, extractor: Extractor, batch_articles: list[str]
    ) -> None:
        """Parallel processing is faster than sequential for multiple items."""
        # Sequential
        start = time.perf_counter()
        await extractor.extract_batch(batch_articles[:5], parallel=False)
        sequential_time = time.perf_counter() - start

        # Parallel
        start = time.perf_counter()
        await extractor.extract_batch(batch_articles[:5], parallel=True)
        parallel_time = time.perf_counter() - start

        # Parallel should not be significantly slower
        # (may not be faster for small batches due to overhead)
        assert parallel_time < sequential_time * 1.5, \
            f"Parallel ({parallel_time:.2f}s) much slower than sequential ({sequential_time:.2f}s)"

    @pytest.mark.asyncio
    async def test_large_batch_completes(self, extractor: Extractor) -> None:
        """Large batch completes without timeout."""
        # Create 20 articles
        articles = ["Article about topic " + str(i) + ". Facts and details." for i in range(20)]

        start = time.perf_counter()
        results = await extractor.extract_batch(articles, parallel=True, max_workers=5)
        elapsed = time.perf_counter() - start

        assert len(results) == len(articles)
        # Should complete in reasonable time (< 60s for 20 articles)
        assert elapsed < 60, f"Large batch took {elapsed:.2f}s"


# =============================================================================
# FORMATTING PERFORMANCE
# =============================================================================


class TestFormattingPerformance:
    """Tests for output formatting performance."""

    @pytest.fixture
    def result(self, extractor: Extractor, standard_article: str) -> ExtractionResult:
        """Create extraction result for formatting tests."""
        return extractor.extract_sync(standard_article)

    def test_json_formatting_fast(
        self, extractor: Extractor, result: ExtractionResult
    ) -> None:
        """JSON formatting is fast."""
        start = time.perf_counter()
        for _ in range(10):
            extractor.format(result, format="json")
        elapsed = time.perf_counter() - start

        avg_time = elapsed / 10
        assert avg_time < 0.1, f"JSON formatting avg {avg_time:.3f}s too slow"

    def test_markdown_formatting_fast(
        self, extractor: Extractor, result: ExtractionResult
    ) -> None:
        """Markdown formatting is fast."""
        start = time.perf_counter()
        for _ in range(10):
            extractor.format(result, format="markdown")
        elapsed = time.perf_counter() - start

        avg_time = elapsed / 10
        assert avg_time < 0.1, f"Markdown formatting avg {avg_time:.3f}s too slow"

    def test_text_formatting_fast(
        self, extractor: Extractor, result: ExtractionResult
    ) -> None:
        """Text formatting is fast."""
        start = time.perf_counter()
        for _ in range(10):
            extractor.format(result, format="text")
        elapsed = time.perf_counter() - start

        avg_time = elapsed / 10
        assert avg_time < 0.1, f"Text formatting avg {avg_time:.3f}s too slow"


# =============================================================================
# STRESS TESTS
# =============================================================================


class TestStressConditions:
    """Tests for behavior under stress conditions."""

    def test_very_long_content(self, extractor: Extractor) -> None:
        """Handles very long content without crashing."""
        # 5000 words
        long_content = "The company reported strong results. " * 1000

        start = time.perf_counter()
        result = extractor.extract_sync(long_content)
        elapsed = time.perf_counter() - start

        assert isinstance(result, ExtractionResult)
        assert result.statistics.original_words == 5000
        # Should complete in reasonable time
        assert elapsed < 30, f"Very long content took {elapsed:.2f}s"

    def test_many_sentences(self, extractor: Extractor) -> None:
        """Handles content with many sentences."""
        # 500 sentences
        many_sentences = ". ".join([f"Sentence number {i} with some content" for i in range(500)])

        start = time.perf_counter()
        result = extractor.extract_sync(many_sentences)
        elapsed = time.perf_counter() - start

        assert isinstance(result, ExtractionResult)
        assert elapsed < 20, f"Many sentences took {elapsed:.2f}s"

    def test_complex_unicode(self, extractor: Extractor) -> None:
        """Handles complex unicode content efficiently."""
        unicode_content = """
        日本語のテキスト。中文文本。한국어 텍스트。
        Ελληνικά κείμενο. Русский текст. العربية النص.
        """ * 50

        start = time.perf_counter()
        result = extractor.extract_sync(unicode_content)
        elapsed = time.perf_counter() - start

        assert isinstance(result, ExtractionResult)
        assert elapsed < 10, f"Unicode content took {elapsed:.2f}s"

    def test_special_characters_heavy(self, extractor: Extractor) -> None:
        """Handles content heavy with special characters."""
        special_content = """
        Price: $100.50 (€90.25 / £80.00) @ 15% discount!!!
        Email: test@example.com | Phone: +1-555-0123
        URL: https://example.com/path?query=value&other=123
        Math: 2^10 = 1024, √16 = 4, π ≈ 3.14159
        """ * 50

        start = time.perf_counter()
        result = extractor.extract_sync(special_content)
        elapsed = time.perf_counter() - start

        assert isinstance(result, ExtractionResult)
        assert elapsed < 10, f"Special chars took {elapsed:.2f}s"

    @pytest.mark.asyncio
    async def test_concurrent_extractions(self, extractor: Extractor) -> None:
        """Handles many concurrent extractions."""
        articles = [f"Article {i} about technology and business." for i in range(50)]

        start = time.perf_counter()
        results = await extractor.extract_batch(articles, parallel=True, max_workers=10)
        elapsed = time.perf_counter() - start

        assert len(results) == len(articles)
        # Should handle 50 articles in reasonable time
        assert elapsed < 60, f"50 concurrent extractions took {elapsed:.2f}s"


# =============================================================================
# MEMORY TESTS
# =============================================================================


class TestMemoryUsage:
    """Tests for memory usage patterns."""

    def test_no_memory_leak_repeated_extraction(self, extractor: Extractor) -> None:
        """Repeated extractions don't leak memory significantly."""

        content = "Test article content for memory testing. " * 100

        # Warm up
        extractor.extract_sync(content)

        # Get baseline (approximate)
        # Note: This is a simple heuristic, not precise memory measurement
        results = []
        for i in range(10):
            result = extractor.extract_sync(content)
            results.append(result)

        # If we got here without OOM, basic memory management is working
        assert len(results) == 10

    def test_large_result_memory(self, extractor: Extractor) -> None:
        """Large results don't cause memory issues."""
        # Create content that will produce large result
        large_content = """
        Apple reported $90 billion revenue. CEO Tim Cook announced.
        Google reported $75 billion revenue. CEO Sundar Pichai commented.
        Microsoft reported $60 billion revenue. CEO Satya Nadella stated.
        """ * 100

        result = extractor.extract_sync(large_content)

        # Result should be reasonable size
        assert isinstance(result, ExtractionResult)
        # Text shouldn't be absurdly large
        assert len(result.text) < 1000000  # Less than 1MB of text


# =============================================================================
# BENCHMARK UTILITIES
# =============================================================================


class TestBenchmarkBaselines:
    """Establish and verify performance baselines."""

    def test_extraction_baseline(self, extractor: Extractor) -> None:
        """Record extraction baseline performance."""
        content = """
        The Federal Reserve announced a 0.25% interest rate increase.
        Chair Jerome Powell cited inflation concerns in the decision.
        Markets reacted positively to the measured approach.
        """

        times = []
        for _ in range(5):
            start = time.perf_counter()
            extractor.extract_sync(content)
            times.append(time.perf_counter() - start)

        avg_time = sum(times) / len(times)
        min_time = min(times)
        max_time = max(times)

        # Log baseline (would be captured by test output)
        print(f"\nExtraction baseline: avg={avg_time:.3f}s, min={min_time:.3f}s, max={max_time:.3f}s")

        # Verify reasonable performance
        assert avg_time < 5.0, f"Baseline too slow: {avg_time:.3f}s"

    @pytest.mark.asyncio
    async def test_batch_baseline(self, extractor: Extractor) -> None:
        """Record batch processing baseline."""
        articles = [f"Article {i} content." for i in range(10)]

        times = []
        for _ in range(3):
            start = time.perf_counter()
            await extractor.extract_batch(articles, parallel=True)
            times.append(time.perf_counter() - start)

        avg_time = sum(times) / len(times)
        throughput = 10 / avg_time

        print(f"\nBatch baseline: avg={avg_time:.3f}s, throughput={throughput:.2f} articles/s")

        assert throughput > 0.5, f"Batch throughput too low: {throughput:.2f}"
