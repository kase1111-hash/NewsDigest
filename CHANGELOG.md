# Changelog

All notable changes to NewsDigest will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- End-to-end test suite with comprehensive tests:
  - `test_extraction_pipeline.py` - Extraction flow and formatters
  - `test_api_endpoints.py` - REST API endpoint testing
  - `test_storage.py` - Cache, database, and analytics storage
  - `test_middleware.py` - Auth, rate limiting, and request tracking
- REST API with FastAPI (endpoints: /health, /extract, /extract/batch, /digest, /compare)
- API middleware for authentication, rate limiting, and request tracking:
  - `APIKeyManager` - API key creation, validation, and revocation
  - `RateLimiter` - Token bucket rate limiting algorithm
  - `RequestTracker` - Request metrics collection
- Storage layer with MemoryCache, FileCache, AnalyticsStore, and SourceStore
- SQLite database persistence layer (`Database` class)
- Monitoring utilities (`HealthMonitor`, `AlertManager`, `MetricsCollector`)
- External integrations:
  - Email notifications (`EmailNotifier`)
  - NewsAPI client (`NewsAPIClient`)
  - Twitter/X integration (`TwitterClient`)
  - Telegram bot integration (`TelegramBot`)
  - Slack integration (`SlackNotifier`)
- CLI commands: extract, compare, stats, digest, sources, watch, analytics, setup
- `ValidationError` exception for input validation
- Polyform Small Business License 1.0.0
- `Config.load()`: reads `~/.newsdigest/config.yml` (or `$NEWSDIGEST_CONFIG`)
  and applies `NEWSDIGEST_*` environment overrides; used by the CLI and API
- `NEWSDIGEST_CORS_ORIGINS` setting for the API
- CLI accepts `-` as SOURCE to read an article from standard input

### Changed
- Extraction modes (`conservative`, `standard`, `aggressive`) now tune the
  analyzers; previously every mode behaved like `standard`
- `Extractor` and the CLI default to the configured mode; unknown modes raise
- `newsdigest setup` writes `~/.newsdigest/config.yml` (the file that is read)
- Only `NEWSDIGEST_`-prefixed environment variables configure NewsDigest
- Emotional language: sensational adjectives are always stripped,
  sensational lead-in clauses and reaction-only sentences are removed, and
  direct quotes are never edited
- Ruff is pinned (CI, pre-commit, dev requirements)

### Fixed
- Circular import in API routes (moved `get_config` to `api/utils.py`)
- Linting issues in API routes and middleware
- API `/extract`, `/compare` and `/extract/batch` failed with a 500 error for
  every text source (`asyncio.run()` inside the server's event loop)
- API ignored the request `mode`, a config passed to `create_app()`, and the
  digest options `max_articles` and `cluster_threshold`
- Plain text: the first wrapped line was taken as the title, cutting the
  first sentence in half; layout whitespace leaked into the output
- HTML: text inside inline tags was extracted twice; class-name heuristics
  removed headlines and could remove whole articles
- Crash (`RecursionError`) on long articles with repeated sentences
- Closing quotes attached to the following sentence
- Duplicate claims per sentence; original density always reported as 0
- SSRF: URL validation now blocks IPv6, link-local/cloud-metadata, CGNAT and
  alternate IPv4 encodings, and re-validates every redirect; RSS feeds are
  fetched through the validated client
- HTML sanitizer missed `<embed>`, `<style>`, inline styles and nested tags;
  pasted text input was not sanitized
- CLI: JSON output was hard-wrapped (invalid JSON), article text was parsed
  as markup, and long raw-text arguments crashed
- CLI and API ignored the user config file and environment variables;
  `Config.save()` wrote files that could not be loaded
- In-memory `Database` lost its tables between calls
- Required secrets never raised; `sk-proj-` keys were not masked
- RSS dates were converted as local time instead of UTC
- CI: lint, type-check and security jobs failed, and the test job lacked
  FastAPI, so tests never ran

## [0.1.0] - 2024-01-15

### Added
- Core semantic extraction engine with 8 analyzers:
  - Filler detection
  - Speculation stripping
  - Source validation
  - Emotional language detection
  - Repetition collapsing
  - Novelty scoring
  - Claims extraction
  - Quote isolation
- Content ingestion from multiple sources:
  - URL fetching with async HTTP client
  - RSS/Atom feed parsing
  - Direct text input
- Output formatters:
  - JSON with detailed metadata
  - Markdown with tables
  - Plain text
- Digest generation with topic clustering and deduplication
- Configuration management system:
  - YAML configuration files
  - Environment variable support
  - Secret management
- Comprehensive error handling with custom exception types
- Logging and telemetry infrastructure
- Metrics collection system
- CI/CD pipeline with GitHub Actions:
  - Automated testing (Python 3.11, 3.12)
  - Code quality checks (ruff, mypy, bandit)
  - Release automation to PyPI
- Docker containerization support
- Pre-commit hooks for code quality
- Semantic versioning with bump2version
- Extensive documentation:
  - Technical specification (SPEC.md)
  - Architecture documentation
  - OpenAPI specification
  - Postman collection

### Infrastructure
- pytest test suite with 483 test functions
- Code coverage requirement of 80%
- Strict type checking with mypy
- Security scanning with bandit

[Unreleased]: https://github.com/kase1111-hash/NewsDigest/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/kase1111-hash/NewsDigest/releases/tag/v0.1.0
