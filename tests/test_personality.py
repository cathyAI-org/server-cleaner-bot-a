"""Core functionality tests for PersonalityRenderer."""
import pytest
from catcord_bots.personality import (
    PersonalityRenderer,
    _FALLBACK_BANK,
    _STATUS_PROMPT_HINTS,
)


class TestPersonalityRenderer:
    """Test suite for PersonalityRenderer class."""

    def _make_renderer(self, **kwargs) -> PersonalityRenderer:
        """Create a renderer with sensible defaults.

        :return: Configured renderer instance
        :rtype: PersonalityRenderer
        """
        defaults = dict(
            prompt_composer_url="http://test",
            character_id="test",
            cathy_api_url="http://test",
            fallback_system_prompt="test",
        )
        defaults.update(kwargs)
        return PersonalityRenderer(**defaults)

    # -- normalisation -----------------------------------------------

    def test_normalize_prefix_removes_quotes(self) -> None:
        """Test that normalization removes wrapping quotes."""
        renderer = self._make_renderer()

        assert renderer._normalize_prefix('"test"') == "test"
        assert renderer._normalize_prefix("'test'") == "test"
        assert renderer._normalize_prefix("test") == "test"

    # -- status label derivation ------------------------------------

    def test_derive_cleanup_done(self) -> None:
        """Test deleted_count > 0 yields cleanup_done."""
        assert PersonalityRenderer._derive_status_label(
            {"actions": {"deleted_count": 3}, "storage_status": "healthy"}
        ) == "cleanup_done"

    def test_derive_tight_no_action(self) -> None:
        """Test tight storage with no deletions yields tight_no_action."""
        for status in ("tight", "warning", "pressure", "critical"):
            assert PersonalityRenderer._derive_status_label(
                {"actions": {"deleted_count": 0}, "storage_status": status}
            ) == "tight_no_action"

    def test_derive_retention_nothing_to_do(self) -> None:
        """Test retention mode with zero candidates yields
        retention_nothing_to_do."""
        assert PersonalityRenderer._derive_status_label(
            {
                "mode": "retention",
                "candidates_count": 0,
                "actions": {"deleted_count": 0},
                "storage_status": "healthy",
            }
        ) == "retention_nothing_to_do"

    def test_derive_healthy_no_action(self) -> None:
        """Test default healthy path."""
        assert PersonalityRenderer._derive_status_label(
            {"actions": {"deleted_count": 0}, "storage_status": "healthy"}
        ) == "healthy_no_action"

    # -- validation --------------------------------------------------

    def test_validate_prefix_rejects_invalid(self) -> None:
        """Test that validation rejects invalid prefixes."""
        renderer = self._make_renderer()

        assert not renderer._validate_prefix("")[0]
        assert not renderer._validate_prefix("Contains 123")[0]
        assert not renderer._validate_prefix("I am a bot")[0]
        assert not renderer._validate_prefix("Matrix room")[0]

    def test_validate_prefix_accepts_valid(self) -> None:
        """Test that validation accepts valid prefixes."""
        renderer = self._make_renderer()

        assert renderer._validate_prefix("Logs clear, Master.")[0]
        assert renderer._validate_prefix(
            "Storage getting tight, Master."
        )[0]
        assert renderer._validate_prefix(
            "Cleanup executed, Master."
        )[0]

    def test_validate_prefix_blocks_action_words_when_no_deletions(
        self,
    ) -> None:
        """Test action words are rejected when deleted_count is 0."""
        renderer = self._make_renderer()

        ok, reason = renderer._validate_prefix(
            "Files deleted, Master.", deleted_count=0
        )
        assert not ok
        assert "claims deletion" in reason

    def test_validate_prefix_allows_action_words_when_deletions(
        self,
    ) -> None:
        """Test action words are allowed when deleted_count > 0."""
        renderer = self._make_renderer()

        ok, _ = renderer._validate_prefix(
            "Old files deleted, Master.", deleted_count=5
        )
        assert ok

    # -- fallback bank -----------------------------------------------

    def test_fallback_prefix_healthy_no_action(self) -> None:
        """Test fallback selects from healthy_no_action bucket."""
        renderer = self._make_renderer()
        payload = {
            "actions": {"deleted_count": 0},
            "storage_status": "healthy",
        }
        result = renderer._get_fallback_prefix(payload)
        assert result in _FALLBACK_BANK["healthy_no_action"]

    def test_fallback_prefix_tight_no_action(self) -> None:
        """Test fallback selects from tight_no_action bucket."""
        renderer = self._make_renderer()
        payload = {
            "actions": {"deleted_count": 0},
            "storage_status": "tight",
        }
        result = renderer._get_fallback_prefix(payload)
        assert result in _FALLBACK_BANK["tight_no_action"]

    def test_fallback_prefix_cleanup_done(self) -> None:
        """Test fallback selects from cleanup_done bucket."""
        renderer = self._make_renderer()
        payload = {
            "actions": {"deleted_count": 5},
            "storage_status": "healthy",
        }
        result = renderer._get_fallback_prefix(payload)
        assert result in _FALLBACK_BANK["cleanup_done"]

    def test_fallback_prefix_retention_nothing_to_do(self) -> None:
        """Test fallback selects from retention_nothing_to_do bucket."""
        renderer = self._make_renderer()
        payload = {
            "mode": "retention",
            "candidates_count": 0,
            "actions": {"deleted_count": 0},
            "storage_status": "healthy",
        }
        result = renderer._get_fallback_prefix(payload)
        assert result in _FALLBACK_BANK["retention_nothing_to_do"]

    def test_fallback_prefix_deterministic_for_same_payload(
        self,
    ) -> None:
        """Test same payload always yields the same fallback."""
        renderer = self._make_renderer()
        payload = {
            "actions": {"deleted_count": 0},
            "storage_status": "healthy",
        }
        a = renderer._get_fallback_prefix(payload)
        b = renderer._get_fallback_prefix(payload)
        assert a == b

    def test_fallback_prefix_varies_with_payload(self) -> None:
        """Test different payloads can produce different fallbacks."""
        renderer = self._make_renderer()
        results = set()
        for i in range(20):
            payload = {
                "actions": {"deleted_count": 0},
                "storage_status": "healthy",
                "run_id": i,
            }
            results.add(renderer._get_fallback_prefix(payload))
        assert len(results) > 1

    # -- status prompt hints ----------------------------------------

    def test_status_prompt_hints_cover_all_buckets(self) -> None:
        """Every fallback bucket has a matching prompt hint."""
        assert set(_FALLBACK_BANK) == set(_STATUS_PROMPT_HINTS)

    # -- rate limiting -----------------------------------------------

    def test_rate_limiting(self) -> None:
        """Test rate limiting functionality."""
        renderer = self._make_renderer(min_seconds_between_calls=10)

        assert not renderer._rate_limited()
        assert renderer._rate_limited()
