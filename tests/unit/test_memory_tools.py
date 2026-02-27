"""
Unit tests for memory_tools (mcp_tools/handlers/memory_tools.py)

Tests cover:
- memory_search: recent scope, longterm scope, auto scope
- memory_get: read specific memory files
- Error handling and edge cases
"""
import os
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta

from mcp_tools.handlers.memory_tools import memory_search, memory_get, memory_write
from api.services.memory_files import MemoryFileManager


@pytest.fixture
def workspace(tmp_path):
    """Create a temporary workspace with some memory files."""
    ws = str(tmp_path / "workspace")
    mgr = MemoryFileManager(workspace_path=ws, retention_days=7)
    today = datetime.now().strftime("%Y-%m-%d")
    mgr.write_longterm("# MEMORY\nUser prefers Python. Project uses FastAPI.")
    mgr.append_daily("Debugged memory search feature. Fixed slug generation.", date=today)
    mgr.write_session_archive("python-fastapi", "# Session\n**User**: How to test FastAPI?\n**Assistant**: Use pytest with httpx.", date=today)
    return ws, mgr


class TestMemorySearch:
    """Test memory_search function."""

    def test_no_manager_returns_error(self):
        with patch("mcp_tools.handlers.memory_tools._get_memory_file_manager", return_value=None), \
             patch("mcp_tools.handlers.memory_tools._search_longterm_memory", return_value=[]):
            result = memory_search(query="test")
        # With no manager, recent search returns [] and longterm mocked empty
        assert "results" in result
        assert result["count"] == 0

    def test_empty_query_returns_error(self):
        result = memory_search(query="")
        assert "error" in result

    def test_recent_scope_finds_matching_files(self, workspace):
        ws_path, mgr = workspace
        with patch("mcp_tools.handlers.memory_tools._get_memory_file_manager", return_value=mgr):
            result = memory_search(query="Python", scope="recent")

        assert result["scope"] == "recent"
        assert result["count"] > 0
        # Should find Python in MEMORY.md and/or archive
        assert any("Python" in r.get("snippet", "") or "python" in r.get("snippet", "").lower()
                    for r in result["results"])

    def test_recent_scope_returns_snippets(self, workspace):
        ws_path, mgr = workspace
        with patch("mcp_tools.handlers.memory_tools._get_memory_file_manager", return_value=mgr):
            result = memory_search(query="FastAPI", scope="recent")

        for r in result["results"]:
            assert "snippet" in r
            assert "path" in r
            assert "score" in r
            assert "source" in r
            assert r["source"] == "local"

    def test_auto_scope_returns_results(self, workspace):
        ws_path, mgr = workspace
        with patch("mcp_tools.handlers.memory_tools._get_memory_file_manager", return_value=mgr):
            result = memory_search(query="FastAPI", scope="auto")

        assert "results" in result
        assert result["count"] > 0

    def test_no_match_returns_empty(self, workspace):
        ws_path, mgr = workspace
        with patch("mcp_tools.handlers.memory_tools._get_memory_file_manager", return_value=mgr):
            result = memory_search(query="quantum computing blockchain", scope="recent")

        assert result["count"] == 0

    def test_max_results_limit(self, workspace):
        ws_path, mgr = workspace
        with patch("mcp_tools.handlers.memory_tools._get_memory_file_manager", return_value=mgr):
            result = memory_search(query="Python", scope="recent", max_results=1)

        assert len(result["results"]) <= 1

    def test_longterm_scope_skips_local(self):
        """Longterm scope should not search local files (searches AgentCore only)."""
        # Mock longterm to return empty (no AgentCore in test env)
        with patch("mcp_tools.handlers.memory_tools._search_longterm_memory", return_value=[]):
            result = memory_search(query="test", scope="longterm")

        assert "results" in result
        # No AgentCore configured in test, so no longterm results
        assert result["count"] == 0


class TestMemoryGet:
    """Test memory_get function."""

    def test_no_manager_returns_error(self):
        with patch("mcp_tools.handlers.memory_tools._get_memory_file_manager", return_value=None):
            result = memory_get(path="MEMORY.md")
        assert "error" in result

    def test_reads_file_successfully(self, workspace):
        ws_path, mgr = workspace
        with patch("mcp_tools.handlers.memory_tools._get_memory_file_manager", return_value=mgr):
            result = memory_get(path="MEMORY.md")

        assert "# MEMORY" in result["text"]
        assert "Python" in result["text"]
        assert result["path"] == "MEMORY.md"

    def test_passes_line_range(self, workspace):
        ws_path, mgr = workspace
        with patch("mcp_tools.handlers.memory_tools._get_memory_file_manager", return_value=mgr):
            result = memory_get(path="MEMORY.md", from_line=2, lines=1)

        # Line 2 of MEMORY.md is "User prefers Python..."
        assert "Python" in result["text"] or "FastAPI" in result["text"]

    def test_empty_path_returns_error(self, workspace):
        ws_path, mgr = workspace
        with patch("mcp_tools.handlers.memory_tools._get_memory_file_manager", return_value=mgr):
            result = memory_get(path="")

        assert result.get("error") or result.get("text") == ""

    def test_file_not_found(self, workspace):
        ws_path, mgr = workspace
        with patch("mcp_tools.handlers.memory_tools._get_memory_file_manager", return_value=mgr):
            result = memory_get(path="nonexistent.md")

        # read_file returns empty text for non-md or nonexistent
        assert result.get("text") == "" or result.get("error")

    def test_reads_memory_subdir_file(self, workspace):
        ws_path, mgr = workspace
        today = datetime.now().strftime("%Y-%m-%d")
        with patch("mcp_tools.handlers.memory_tools._get_memory_file_manager", return_value=mgr):
            result = memory_get(path=f"memory/{today}.md")

        assert "Debugged" in result["text"]


class TestMemoryWrite:
    """Test memory_write function."""

    def test_no_manager_returns_error(self):
        with patch("mcp_tools.handlers.memory_tools._get_memory_file_manager", return_value=None):
            result = memory_write(target="daily", content="test note")
        assert "error" in result

    def test_empty_content_returns_error(self):
        result = memory_write(target="daily", content="")
        assert "error" in result

    def test_whitespace_only_content_returns_error(self):
        result = memory_write(target="daily", content="   \n  ")
        assert "error" in result

    def test_unknown_target_returns_error(self, workspace):
        ws_path, mgr = workspace
        with patch("mcp_tools.handlers.memory_tools._get_memory_file_manager", return_value=mgr):
            result = memory_write(target="invalid", content="test")
        assert "error" in result
        assert "invalid" in result["error"]

    def test_daily_target_appends(self, workspace):
        ws_path, mgr = workspace
        with patch("mcp_tools.handlers.memory_tools._get_memory_file_manager", return_value=mgr):
            result = memory_write(target="daily", content="New daily note")
        assert result["success"] is True
        assert result["target"] == "daily"
        assert "path" in result
        assert result["chars"] == len("New daily note")

    def test_daily_target_normalizes_case(self, workspace):
        ws_path, mgr = workspace
        with patch("mcp_tools.handlers.memory_tools._get_memory_file_manager", return_value=mgr):
            result = memory_write(target="  Daily ", content="case test")
        assert result["success"] is True
        assert result["target"] == "daily"

    def test_longterm_target_appends_to_memory_md(self, workspace):
        ws_path, mgr = workspace
        with patch("mcp_tools.handlers.memory_tools._get_memory_file_manager", return_value=mgr):
            result = memory_write(target="longterm", content="## New Section\nImportant fact.")
        assert result["success"] is True
        assert result["target"] == "longterm"
        assert "path" in result
        # Chars should include existing content + new content
        assert result["chars"] > len("## New Section\nImportant fact.")

    def test_longterm_preserves_existing_content(self, workspace):
        ws_path, mgr = workspace
        with patch("mcp_tools.handlers.memory_tools._get_memory_file_manager", return_value=mgr):
            memory_write(target="longterm", content="## Added Section")
            result = memory_get(path="MEMORY.md")
        # Should contain both old and new content
        assert "# MEMORY" in result["text"]
        assert "## Added Section" in result["text"]

    def test_longterm_on_empty_memory(self, tmp_path):
        """Writing longterm when MEMORY.md doesn't exist yet."""
        ws = str(tmp_path / "empty_ws")
        mgr = MemoryFileManager(workspace_path=ws, retention_days=7)
        with patch("mcp_tools.handlers.memory_tools._get_memory_file_manager", return_value=mgr):
            result = memory_write(target="longterm", content="# Fresh Memory")
        assert result["success"] is True
        # Verify content was written
        with patch("mcp_tools.handlers.memory_tools._get_memory_file_manager", return_value=mgr):
            got = memory_get(path="MEMORY.md")
        assert "# Fresh Memory" in got["text"]
