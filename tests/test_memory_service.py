"""Tests for memory service."""
import pytest
import tempfile
from pathlib import Path


def test_health():
    """Test health endpoint."""
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent / "services" / "memory"))
    
    with tempfile.TemporaryDirectory() as tmpdir:
        import main
        main.DB_PATH = Path(tmpdir) / "test.db"
        main.init_db()
        
        from fastapi.testclient import TestClient
        with TestClient(main.app) as client:
            response = client.get("/health")
            assert response.status_code == 200
            assert response.json() == {"status": "ok"}


def test_ingest_event():
    """Test event ingestion."""
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent / "services" / "memory"))
    
    with tempfile.TemporaryDirectory() as tmpdir:
        import main
        main.DB_PATH = Path(tmpdir) / "test.db"
        main.init_db()
        
        from fastapi.testclient import TestClient
        with TestClient(main.app) as client:
            response = client.post(
                "/v1/events/ingest",
                json={
                    "source": "test",
                    "external_user_id": "test_user",
                    "person_id": "person_123",
                    "role": "user",
                    "content": "Test message",
                    "ts": "2024-01-01T12:00:00+00:00",
                },
            )
            assert response.status_code == 200
            data = response.json()
            assert "event_id" in data
            assert data["person_id"] == "person_123"


def test_query_memory():
    """Test memory query."""
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent / "services" / "memory"))
    
    with tempfile.TemporaryDirectory() as tmpdir:
        import main
        main.DB_PATH = Path(tmpdir) / "test.db"
        main.init_db()
        
        from fastapi.testclient import TestClient
        with TestClient(main.app) as client:
            # First ingest an event
            client.post(
                "/v1/events/ingest",
                json={
                    "source": "test",
                    "external_user_id": "test_user",
                    "person_id": "person_123",
                    "role": "user",
                    "content": "Test message",
                    "ts": "2024-01-01T12:00:00+00:00",
                },
            )
            
            # Then query
            response = client.post(
                "/v1/memory/query",
                json={
                    "person_id": "person_123",
                    "k": 10,
                },
            )
            assert response.status_code == 200
            data = response.json()
            assert "results" in data
            assert len(data["results"]) > 0
            assert data["results"][0]["content"] == "Test message"
