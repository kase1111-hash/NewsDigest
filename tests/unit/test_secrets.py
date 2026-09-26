"""Tests for secrets management."""

import pytest

from newsdigest.config.secrets import (
    EnvLoader,
    SecretMasker,
    SecretsManager,
    SecretValue,
    get_env,
    get_secret,
    init_env,
    mask_secrets,
    register_secret,
)


class TestSecretValue:
    """Tests for SecretValue wrapper class."""

    def test_get_value(self):
        """Test getting the secret value."""
        secret = SecretValue("my-secret-key")
        assert secret.get() == "my-secret-key"

    def test_str_hides_value(self):
        """Test that str() hides the value."""
        secret = SecretValue("my-secret-key")
        assert str(secret) == "SecretValue(****)"
        assert "my-secret-key" not in str(secret)

    def test_repr_hides_value(self):
        """Test that repr() hides the value."""
        secret = SecretValue("my-secret-key")
        assert "my-secret-key" not in repr(secret)

    def test_none_value(self):
        """Test handling of None value."""
        secret = SecretValue(None)
        assert secret.get() is None
        assert str(secret) == "SecretValue(None)"

    def test_bool_true_when_has_value(self):
        """Test bool is True when has value."""
        secret = SecretValue("value")
        assert bool(secret) is True

    def test_bool_false_when_empty(self):
        """Test bool is False when empty."""
        secret = SecretValue("")
        assert bool(secret) is False

    def test_bool_false_when_none(self):
        """Test bool is False when None."""
        secret = SecretValue(None)
        assert bool(secret) is False

    def test_equality(self):
        """Test equality comparison."""
        secret1 = SecretValue("value")
        secret2 = SecretValue("value")
        secret3 = SecretValue("different")

        assert secret1 == secret2
        assert secret1 != secret3

    def test_hash(self):
        """Test hashing for use in sets/dicts."""
        secret1 = SecretValue("value")
        secret2 = SecretValue("value")

        # Should be usable in sets
        s = {secret1, secret2}
        assert len(s) == 1


class TestEnvLoader:
    """Tests for EnvLoader class."""

    def test_get_env_var(self, monkeypatch):
        """Test getting environment variable."""
        monkeypatch.setenv("NEWSDIGEST_TEST_VAR", "test_value")
        loader = EnvLoader()
        result = loader.get("TEST_VAR")
        assert result == "test_value"

    def test_get_with_default(self):
        """Test getting with default value."""
        loader = EnvLoader()
        result = loader.get("NONEXISTENT_VAR", default="default")
        assert result == "default"

    def test_get_required_raises(self):
        """Test that required missing var raises."""
        loader = EnvLoader()
        with pytest.raises(ValueError, match="Required environment variable"):
            loader.get("NONEXISTENT_REQUIRED", required=True)

    def test_get_with_cast(self, monkeypatch):
        """Test getting with type cast."""
        monkeypatch.setenv("NEWSDIGEST_NUM", "42")
        loader = EnvLoader()
        result = loader.get("NUM", cast=int)
        assert result == 42
        assert isinstance(result, int)

    def test_get_bool_true(self, monkeypatch):
        """Test getting boolean true values."""
        loader = EnvLoader()
        for value in ["true", "1", "yes", "on"]:
            monkeypatch.setenv("NEWSDIGEST_BOOL", value)
            assert loader.get_bool("BOOL") is True

    def test_get_bool_false(self, monkeypatch):
        """Test getting boolean false values."""
        loader = EnvLoader()
        for value in ["false", "0", "no", "off"]:
            monkeypatch.setenv("NEWSDIGEST_BOOL", value)
            assert loader.get_bool("BOOL") is False

    def test_get_int(self, monkeypatch):
        """Test getting integer value."""
        monkeypatch.setenv("NEWSDIGEST_INT", "123")
        loader = EnvLoader()
        result = loader.get_int("INT")
        assert result == 123

    def test_get_int_invalid_returns_default(self, monkeypatch):
        """Test getting invalid integer returns default."""
        monkeypatch.setenv("NEWSDIGEST_INT", "not-a-number")
        loader = EnvLoader()
        result = loader.get_int("INT", default=99)
        assert result == 99

    def test_get_float(self, monkeypatch):
        """Test getting float value."""
        monkeypatch.setenv("NEWSDIGEST_FLOAT", "3.14")
        loader = EnvLoader()
        result = loader.get_float("FLOAT")
        assert result == 3.14

    def test_get_list(self, monkeypatch):
        """Test getting list value."""
        monkeypatch.setenv("NEWSDIGEST_LIST", "a,b,c")
        loader = EnvLoader()
        result = loader.get_list("LIST")
        assert result == ["a", "b", "c"]

    def test_get_list_custom_separator(self, monkeypatch):
        """Test getting list with custom separator."""
        monkeypatch.setenv("NEWSDIGEST_LIST", "a;b;c")
        loader = EnvLoader()
        result = loader.get_list("LIST", separator=";")
        assert result == ["a", "b", "c"]

    def test_get_list_default(self):
        """Test getting list default value."""
        loader = EnvLoader()
        result = loader.get_list("NONEXISTENT")
        assert result == []

    def test_get_secret(self, monkeypatch):
        """Test getting secret value."""
        monkeypatch.setenv("NEWSDIGEST_API_KEY", "secret-key")
        loader = EnvLoader()
        result = loader.get_secret("API_KEY")
        assert isinstance(result, SecretValue)
        assert result.get() == "secret-key"

    def test_custom_prefix(self, monkeypatch):
        """Test loader with custom prefix."""
        monkeypatch.setenv("MYAPP_VAR", "value")
        loader = EnvLoader(prefix="MYAPP_")
        result = loader.get("VAR")
        assert result == "value"


class TestSecretsManager:
    """Tests for SecretsManager base class."""

    def test_get_secret_from_env(self, monkeypatch):
        """Test getting secret from environment (fallback)."""
        monkeypatch.setenv("TEST_SECRET", "env-value")
        manager = SecretsManager()
        result = manager.get_secret("TEST_SECRET")
        assert isinstance(result, SecretValue)
        assert result.get() == "env-value"

    def test_caching(self, monkeypatch):
        """Test that secrets are cached."""
        monkeypatch.setenv("CACHED_SECRET", "cached-value")
        manager = SecretsManager(cache_ttl=300)

        # First call
        manager.get_secret("CACHED_SECRET")

        # Change env var
        monkeypatch.setenv("CACHED_SECRET", "new-value")

        # Should still return cached value
        result2 = manager.get_secret("CACHED_SECRET")
        assert result2.get() == "cached-value"

    def test_clear_cache(self, monkeypatch):
        """Test clearing cache."""
        monkeypatch.setenv("CACHED_SECRET", "original")
        manager = SecretsManager()

        manager.get_secret("CACHED_SECRET")
        manager.clear_cache()
        monkeypatch.setenv("CACHED_SECRET", "updated")

        result = manager.get_secret("CACHED_SECRET")
        assert result.get() == "updated"

    def test_required_missing_raises(self):
        """Test that required missing secret raises."""
        manager = SecretsManager()
        with pytest.raises(ValueError, match="Required secret"):
            manager.get_secret("NONEXISTENT_SECRET", required=True)


class TestSecretMasker:
    """Tests for SecretMasker class."""

    def test_mask_registered_secret(self):
        """Test masking registered secrets."""
        masker = SecretMasker()
        masker.register_secret("my-super-secret-key")

        text = "API key is my-super-secret-key"
        result = masker.mask(text)

        assert "my-super-secret-key" not in result
        assert "****" in result

    def test_mask_api_key_pattern(self):
        """Test masking API key patterns."""
        masker = SecretMasker()
        text = 'api_key: "sk-1234567890abcdef1234"'
        result = masker.mask(text)
        assert "sk-1234567890abcdef1234" not in result

    def test_mask_bearer_token(self):
        """Test masking bearer tokens."""
        masker = SecretMasker()
        text = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
        result = masker.mask(text)
        assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in result

    def test_mask_openai_key(self):
        """Test masking OpenAI API keys."""
        masker = SecretMasker()
        text = "key = sk-proj-1234567890abcdefghijklmnop"
        result = masker.mask(text)
        assert "sk-proj-1234567890abcdefghijklmnop" not in result

    def test_mask_github_token(self):
        """Test masking GitHub tokens."""
        masker = SecretMasker()
        text = "token: ghp_1234567890abcdefghijklmnopqrstuvwxyz"
        result = masker.mask(text)
        assert "ghp_1234567890abcdefghijklmnopqrstuvwxyz" not in result

    def test_no_masking_normal_text(self):
        """Test that normal text is not masked."""
        masker = SecretMasker()
        text = "This is normal text without secrets."
        result = masker.mask(text)
        assert result == text

    def test_short_secrets_ignored(self):
        """Test that short strings are not registered as secrets."""
        masker = SecretMasker()
        masker.register_secret("abc")  # Too short
        text = "abc is here"
        result = masker.mask(text)
        # Short secrets (< 4 chars) should not be masked
        assert "abc" in result


class TestConvenienceFunctions:
    """Tests for module-level convenience functions."""

    def test_get_env_function(self, monkeypatch):
        """Test get_env convenience function."""
        monkeypatch.setenv("NEWSDIGEST_MY_VAR", "my_value")
        init_env()  # Reset loader
        result = get_env("MY_VAR")
        assert result == "my_value"

    def test_get_secret_function(self, monkeypatch):
        """Test get_secret convenience function."""
        monkeypatch.setenv("NEWSDIGEST_MY_SECRET", "secret")
        init_env()  # Reset loader
        result = get_secret("MY_SECRET")
        assert isinstance(result, SecretValue)
        assert result.get() == "secret"

    def test_mask_secrets_function(self):
        """Test mask_secrets convenience function."""
        register_secret("my-long-secret-value")
        text = "Secret is my-long-secret-value here"
        result = mask_secrets(text)
        assert "my-long-secret-value" not in result

    def test_init_env_with_prefix(self, monkeypatch):
        """Test init_env with custom prefix."""
        monkeypatch.setenv("CUSTOM_VAR", "custom_value")
        loader = init_env(prefix="CUSTOM_")
        result = loader.get("VAR")
        assert result == "custom_value"
