"""
Unit tests for memory router API endpoints (api/routers/memory.py)

Tests cover:
- POST /v1/memory/archive — session archiving endpoint
- GET /v1/memory/files — list memory files
- POST /v1/memory/cleanup — cleanup old memory files
"""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from httpx import AsyncClient, ASGITransport

from api.main import app


@pytest.fixture
async def client():
    """Create an async test client that bypasses lifespan."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


class TestArchiveEndpoint:
    """Test POST /v1/memory/archive."""

    @pytest.mark.asyncio
    async def test_successful_archive(self, client):
        mock_result = {
            "archived": True,
            "path": "memory/2026-02-26-test.md",
            "slug": "test",
            "message_count": 5,
            "session_id": "session-123",
        }
        with patch("api.services.memory_archiver.archive_session", new_callable=AsyncMock, return_value=mock_result):
            response = await client.post("/v1/memory/archive", json={
                "session_id": "session-123",
                "message_count": 15,
            })

        assert response.status_code == 200
        data = response.json()
        assert data["archived"] is True
        assert data["session_id"] == "session-123"

    @pytest.mark.asyncio
    async def test_archive_no_messages(self, client):
        mock_result = {"archived": False, "reason": "no_messages", "session_id": "empty"}
        with patch("api.services.memory_archiver.archive_session", new_callable=AsyncMock, return_value=mock_result):
            response = await client.post("/v1/memory/archive", json={
                "session_id": "empty",
            })

        assert response.status_code == 200
        data = response.json()
        assert data["archived"] is False

    @pytest.mark.asyncio
    async def test_archive_missing_session_id(self, client):
        response = await client.post("/v1/memory/archive", json={})
        assert response.status_code == 422  # Validation error

    @pytest.mark.asyncio
    async def test_archive_custom_message_count(self, client):
        mock_result = {"archived": True, "message_count": 5, "session_id": "s1", "path": "x", "slug": "y"}
        with patch("api.services.memory_archiver.archive_session", new_callable=AsyncMock, return_value=mock_result):
            response = await client.post("/v1/memory/archive", json={
                "session_id": "s1",
                "message_count": 5,
            })

        assert response.status_code == 200


class TestFilesEndpoint:
    """Test GET /v1/memory/files."""

    @pytest.mark.asyncio
    async def test_list_files_success(self, client):
        mock_mgr = MagicMock()
        mock_mgr.list_files.return_value = [
            {"path": "MEMORY.md", "size": 256, "modified": "2026-02-26T10:00:00", "type": "longterm"},
            {"path": "memory/2026-02-26.md", "size": 512, "modified": "2026-02-26T12:00:00", "type": "daily"},
        ]
        mock_mgr.workspace_dir = "/home/user/.springo/workspace"

        with patch("api.services.memory_files.get_memory_file_manager", return_value=mock_mgr):
            response = await client.get("/v1/memory/files")

        assert response.status_code == 200
        data = response.json()
        assert len(data["files"]) == 2
        assert data["workspace"] == "/home/user/.springo/workspace"

    @pytest.mark.asyncio
    async def test_list_files_no_manager(self, client):
        with patch("api.services.memory_files.get_memory_file_manager", return_value=None):
            response = await client.get("/v1/memory/files")

        assert response.status_code == 200
        data = response.json()
        assert data["files"] == []
        assert "error" in data

    @pytest.mark.asyncio
    async def test_list_files_empty(self, client):
        mock_mgr = MagicMock()
        mock_mgr.list_files.return_value = []
        mock_mgr.workspace_dir = "/tmp/workspace"

        with patch("api.services.memory_files.get_memory_file_manager", return_value=mock_mgr):
            response = await client.get("/v1/memory/files")

        assert response.status_code == 200
        data = response.json()
        assert data["files"] == []


class TestCleanupEndpoint:
    """Test POST /v1/memory/cleanup."""

    @pytest.mark.asyncio
    async def test_cleanup_removes_old_files(self, client):
        mock_mgr = MagicMock()
        mock_mgr.cleanup_old_files.return_value = ["2026-02-10.md", "2026-02-11-old-topic.md"]

        with patch("api.services.memory_files.get_memory_file_manager", return_value=mock_mgr):
            response = await client.post("/v1/memory/cleanup")

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 2
        assert len(data["removed"]) == 2

    @pytest.mark.asyncio
    async def test_cleanup_nothing_to_remove(self, client):
        mock_mgr = MagicMock()
        mock_mgr.cleanup_old_files.return_value = []

        with patch("api.services.memory_files.get_memory_file_manager", return_value=mock_mgr):
            response = await client.post("/v1/memory/cleanup")

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 0

    @pytest.mark.asyncio
    async def test_cleanup_no_manager(self, client):
        with patch("api.services.memory_files.get_memory_file_manager", return_value=None):
            response = await client.post("/v1/memory/cleanup")

        assert response.status_code == 200
        data = response.json()
        assert data["removed"] == []
        assert "error" in data
