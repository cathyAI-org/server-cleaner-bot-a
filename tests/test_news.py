"""Tests for news bot."""
import pytest
from news.format import format_digest
from news.state import payload_fingerprint, should_send
import tempfile
import os
import sys
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


def test_format_digest_empty():
    """Test formatting empty digest."""
    payload = {"mode": "daily_digest", "sections": []}
    result = format_digest(payload)
    assert "No recent news items found" in result


def test_format_digest_with_items():
    """Test formatting digest with items."""
    payload = {
        "mode": "daily_digest",
        "sections": [
            {
                "name": "tech",
                "items": [
                    {
                        "title": "Test Article",
                        "source": "Test Source",
                        "url": "https://example.com/test",
                        "published_at": "2024-01-01T12:00:00+00:00",
                        "snippet": "Test snippet",
                    }
                ],
            }
        ],
    }
    result = format_digest(payload)
    assert "Test Article" in result
    assert "Test Source" in result
    assert "https://example.com/test" in result
    assert "Test snippet" in result


def test_format_digest_with_ai_prefix():
    """Test formatting with AI prefix."""
    payload = {"mode": "daily_digest", "sections": []}
    result = format_digest(payload, ai_prefix="Good morning, Master.")
    assert "Delilah: Good morning, Master." in result


def test_payload_fingerprint_stable():
    """Test fingerprint is stable for same payload."""
    payload = {
        "mode": "daily_digest",
        "sections": [
            {
                "name": "tech",
                "items": [
                    {
                        "url": "https://example.com/1",
                        "published_at": "2024-01-01T12:00:00+00:00",
                    }
                ],
            }
        ],
    }
    fp1 = payload_fingerprint(payload)
    fp2 = payload_fingerprint(payload)
    assert fp1 == fp2


def test_payload_fingerprint_changes():
    """Test fingerprint changes with different content."""
    payload1 = {
        "mode": "daily_digest",
        "sections": [
            {"name": "tech", "items": [{"url": "https://example.com/1"}]}
        ],
    }
    payload2 = {
        "mode": "daily_digest",
        "sections": [
            {"name": "tech", "items": [{"url": "https://example.com/2"}]}
        ],
    }
    fp1 = payload_fingerprint(payload1)
    fp2 = payload_fingerprint(payload2)
    assert fp1 != fp2


def test_should_send_first_time():
    """Test should send on first run."""
    with tempfile.TemporaryDirectory() as tmpdir:
        state_path = os.path.join(tmpdir, "test.fp")
        assert should_send(state_path, "abc123", False)


def test_should_send_dedupe():
    """Test deduplication works."""
    with tempfile.TemporaryDirectory() as tmpdir:
        state_path = os.path.join(tmpdir, "test.fp")
        assert should_send(state_path, "abc123", False)
        assert not should_send(state_path, "abc123", False)


def test_should_send_force():
    """Test force override works."""
    with tempfile.TemporaryDirectory() as tmpdir:
        state_path = os.path.join(tmpdir, "test.fp")
        should_send(state_path, "abc123", False)
        assert should_send(state_path, "abc123", True)
