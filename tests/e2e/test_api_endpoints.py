"""End-to-end tests for API endpoints.

Tests the complete API flow including request/response handling.
"""

import pytest
from fastapi.testclient import TestClient

from newsdigest.api.app import create_app


class TestHealthEndpoint:
    """Tests for the health check endpoint."""

    @pytest.fixture
    def client(self) -> TestClient:
        """Create a test client."""
        app = create_app(enable_auth=False, enable_rate_limit=False)
        return TestClient(app)

    def test_health_check_returns_200(self, client: TestClient):
        """Test health endpoint returns 200."""
        response = client.get("/api/v1/health")
        assert response.status_code == 200

    def test_health_check_returns_status(self, client: TestClient):
        """Test health endpoint returns status field."""
        response = client.get("/api/v1/health")
        data = response.json()

        assert "status" in data
        assert data["status"] == "healthy"

    def test_health_check_returns_version(self, client: TestClient):
        """Test health endpoint returns version."""
        response = client.get("/api/v1/health")
        data = response.json()

        assert "version" in data
        assert isinstance(data["version"], str)

    def test_health_check_returns_timestamp(self, client: TestClient):
        """Test health endpoint returns timestamp."""
        response = client.get("/api/v1/health")
        data = response.json()

        assert "timestamp" in data


class TestExtractEndpoint:
    """Tests for the extract endpoint."""

    @pytest.fixture
    def client(self) -> TestClient:
        """Create a test client."""
        app = create_app(enable_auth=False, enable_rate_limit=False)
        return TestClient(app)

    @pytest.fixture
    def sample_text(self) -> str:
        """Sample text for extraction."""
        return (
            "In a shocking development, the company reported $50 million in revenue. "
            "CEO John Smith said, 'We exceeded expectations.' "
            "Sources suggest profits might double next year."
        )

    def test_extract_text_success(self, client: TestClient, sample_text: str):
        """Test extraction from text succeeds."""
        response = client.post(
            "/api/v1/extract",
            json={"source": sample_text},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "result" in data

    def test_extract_returns_content(self, client: TestClient, sample_text: str):
        """Test extraction returns content."""
        response = client.post(
            "/api/v1/extract",
            json={"source": sample_text},
        )

        data = response.json()
        result = data["result"]

        assert "content" in result
        assert len(result["content"]) > 0

    def test_extract_returns_statistics(self, client: TestClient, sample_text: str):
        """Test extraction returns statistics."""
        response = client.post(
            "/api/v1/extract",
            json={"source": sample_text},
        )

        data = response.json()
        result = data["result"]

        assert "statistics" in result
        stats = result["statistics"]
        assert "original_words" in stats
        assert "compressed_words" in stats
        assert "compression_ratio" in stats

    def test_extract_with_mode(self, client: TestClient, sample_text: str):
        """Test extraction with mode parameter."""
        response = client.post(
            "/api/v1/extract",
            json={
                "source": sample_text,
                "mode": "aggressive",
            },
        )

        assert response.status_code == 200

    def test_extract_invalid_source(self, client: TestClient):
        """Test extraction with empty source fails."""
        response = client.post(
            "/api/v1/extract",
            json={"source": ""},
        )

        # Should fail validation
        assert response.status_code in [400, 422]

    def test_extract_missing_source(self, client: TestClient):
        """Test extraction without source fails."""
        response = client.post(
            "/api/v1/extract",
            json={},
        )

        assert response.status_code == 422


class TestBatchExtractEndpoint:
    """Tests for the batch extract endpoint."""

    @pytest.fixture
    def client(self) -> TestClient:
        """Create a test client."""
        app = create_app(enable_auth=False, enable_rate_limit=False)
        return TestClient(app)

    def test_batch_extract_success(self, client: TestClient):
        """Test batch extraction succeeds."""
        sources = [
            "Company A reported $10 million revenue. CEO said results were good.",
            "Company B announced new product. Analysts expect growth.",
        ]

        response = client.post(
            "/api/v1/extract/batch",
            json={"sources": sources},
        )

        assert response.status_code == 200
        data = response.json()

        assert "results" in data
        assert len(data["results"]) == 2

    def test_batch_extract_returns_summary(self, client: TestClient):
        """Test batch extraction returns summary."""
        sources = [
            "First article content here.",
            "Second article content here.",
        ]

        response = client.post(
            "/api/v1/extract/batch",
            json={"sources": sources},
        )

        data = response.json()

        assert "summary" in data
        summary = data["summary"]
        assert "total" in summary
        assert summary["total"] == 2

    def test_batch_extract_with_max_concurrent(self, client: TestClient):
        """Test batch extraction respects max_concurrent."""
        sources = ["Article " + str(i) for i in range(5)]

        response = client.post(
            "/api/v1/extract/batch",
            json={
                "sources": sources,
                "max_concurrent": 2,
            },
        )

        assert response.status_code == 200


class TestCompareEndpoint:
    """Tests for the compare endpoint."""

    @pytest.fixture
    def client(self) -> TestClient:
        """Create a test client."""
        app = create_app(enable_auth=False, enable_rate_limit=False)
        return TestClient(app)

    def test_compare_success(self, client: TestClient):
        """Test compare endpoint succeeds."""
        text = (
            "In a shocking development, profits rose 20%. "
            "The CEO said, 'Results exceeded expectations.' "
            "This might signal future growth."
        )

        response = client.post(
            "/api/v1/compare",
            json={"source": text},
        )

        assert response.status_code == 200

    def test_compare_returns_original(self, client: TestClient):
        """Test compare returns original text."""
        text = "Simple test article content."

        response = client.post(
            "/api/v1/compare",
            json={"source": text},
        )

        data = response.json()
        assert "original" in data

    def test_compare_returns_compressed(self, client: TestClient):
        """Test compare returns compressed text."""
        text = "Simple test article content."

        response = client.post(
            "/api/v1/compare",
            json={"source": text},
        )

        data = response.json()
        assert "compressed" in data

    def test_compare_returns_diff(self, client: TestClient):
        """Test compare returns diff."""
        text = (
            "In a shocking announcement, the company grew. "
            "Revenue was $100 million."
        )

        response = client.post(
            "/api/v1/compare",
            json={"source": text},
        )

        data = response.json()
        assert "diff" in data
        assert isinstance(data["diff"], list)


class TestDigestEndpoint:
    """Tests for the digest endpoint."""

    @pytest.fixture
    def client(self) -> TestClient:
        """Create a test client."""
        app = create_app(enable_auth=False, enable_rate_limit=False)
        return TestClient(app)

    def test_digest_requires_sources(self, client: TestClient):
        """Test digest requires sources."""
        response = client.post(
            "/api/v1/digest",
            json={"sources": []},
        )

        # Empty sources should fail
        assert response.status_code in [400, 422]


class TestAPIErrorHandling:
    """Tests for API error handling."""

    @pytest.fixture
    def client(self) -> TestClient:
        """Create a test client."""
        app = create_app(enable_auth=False, enable_rate_limit=False)
        return TestClient(app)

    def test_invalid_endpoint_returns_404(self, client: TestClient):
        """Test invalid endpoint returns 404."""
        response = client.get("/api/v1/nonexistent")
        assert response.status_code == 404

    def test_wrong_method_returns_405(self, client: TestClient):
        """Test wrong HTTP method returns 405."""
        response = client.get("/api/v1/extract")
        assert response.status_code == 405

    def test_invalid_json_returns_422(self, client: TestClient):
        """Test invalid JSON returns 422."""
        response = client.post(
            "/api/v1/extract",
            content="not valid json",
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 422

    def test_error_response_format(self, client: TestClient):
        """Test error responses have correct format."""
        response = client.post(
            "/api/v1/extract",
            json={},
        )

        assert response.status_code == 422
        data = response.json()

        # FastAPI validation errors have 'detail'
        assert "detail" in data


class TestAPIDocumentation:
    """Tests for API documentation endpoints."""

    @pytest.fixture
    def client(self) -> TestClient:
        """Create a test client."""
        app = create_app(enable_auth=False, enable_rate_limit=False)
        return TestClient(app)

    def test_openapi_available(self, client: TestClient):
        """Test OpenAPI spec is available."""
        response = client.get("/openapi.json")
        assert response.status_code == 200

        data = response.json()
        assert "openapi" in data
        assert "paths" in data

    def test_docs_available(self, client: TestClient):
        """Test Swagger UI is available."""
        response = client.get("/docs")
        assert response.status_code == 200

    def test_redoc_available(self, client: TestClient):
        """Test ReDoc is available."""
        response = client.get("/redoc")
        assert response.status_code == 200


class TestExtractionOptions:
    """Tests that request options and app config reach the extractor."""

    @pytest.fixture
    def client(self) -> TestClient:
        """Create a test client (running the app lifespan)."""
        app = create_app(enable_auth=False, enable_rate_limit=False)
        with TestClient(app) as client:
            yield client

    def _content(self, client: TestClient, path: str, mode: str) -> str:
        response = client.post(
            path,
            json={
                "source": "The dangerous storm hit the Florida coast on Monday, "
                "officials said.",
                "mode": mode,
            },
        )
        assert response.status_code == 200
        data = response.json()
        return data["result"]["content"] if "result" in data else data["compressed"]

    @pytest.mark.parametrize("path", ["/api/v1/extract", "/api/v1/compare"])
    def test_mode_is_honored(self, client: TestClient, path: str):
        """Test the request's mode changes the extraction."""
        assert "dangerous" in self._content(client, path, "standard")
        assert "dangerous" not in self._content(client, path, "aggressive")

    def test_batch_mode_is_honored(self, client: TestClient):
        """Test batch extraction uses the request's mode."""
        response = client.post(
            "/api/v1/extract/batch",
            json={
                "sources": ["The dangerous storm hit Florida on Monday, officials said."],
                "mode": "aggressive",
            },
        )
        item = response.json()["results"][0]
        assert item["success"] is True
        assert "dangerous" not in item["result"]["content"]

    def test_internal_url_rejected_with_source(self, client: TestClient):
        """Test SSRF targets are refused and the error names the source."""
        url = "http://169.254.169.254/latest/meta-data/"
        response = client.post("/api/v1/extract", json={"source": url})

        assert response.status_code == 422
        data = response.json()
        assert data["error"] == "ingest_error"
        assert data["details"]["source"] == url

    def test_empty_compare_source_rejected(self, client: TestClient):
        """Test compare validates its input like extract does."""
        response = client.post("/api/v1/compare", json={"source": ""})
        assert response.status_code == 422


class TestAppConfig:
    """Tests for application configuration handling."""

    def test_passed_config_survives_startup(self):
        """Test the lifespan handler doesn't replace a config given to create_app."""
        from newsdigest.config.settings import Config  # noqa: PLC0415

        config = Config(cache_ttl=123)
        app = create_app(config=config, enable_rate_limit=False)
        with TestClient(app):
            assert app.state.config is config
            assert app.state.cache._default_ttl == 123

    def test_cache_disabled(self):
        """Test cache_enabled=False creates no cache."""
        from newsdigest.config.settings import Config  # noqa: PLC0415

        app = create_app(config=Config(cache_enabled=False), enable_rate_limit=False)
        with TestClient(app):
            assert app.state.cache is None
