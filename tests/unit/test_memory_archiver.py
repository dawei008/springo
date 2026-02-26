"""
Unit tests for memory_archiver (api/services/memory_archiver.py)

Tests cover:
- Reading recent messages from JSONL session files
- Slug generation from conversation content
- Archive formatting to Markdown
- End-to-end archive_session flow
"""
import json
import os
import pytest
import tempfile
from unittest.mock import patch, MagicMock
from datetime import datetime

from api.services.memory_archiver import (
    _read_recent_messages,
    _generate_slug,
    _format_archive,
    archive_session,
    DEFAULT_MESSAGE_COUNT,
)


@pytest.fixture
def sessions_dir(tmp_path):
    """Create a temporary sessions directory."""
    d = str(tmp_path / "sessions")
    os.makedirs(d, exist_ok=True)
    return d


def _create_session_jsonl(sessions_dir: str, session_id: str, entries: list) -> str:
    """Helper: create a session directory with a JSONL file."""
    session_dir = os.path.join(sessions_dir, session_id)
    os.makedirs(session_dir, exist_ok=True)
    jsonl_path = os.path.join(session_dir, f"{session_id}.jsonl")
    with open(jsonl_path, "w", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return jsonl_path


class TestReadRecentMessages:
    """Test _read_recent_messages function."""

    def test_nonexistent_session(self, sessions_dir):
        with patch("api.services.memory_archiver.os.path.expanduser", return_value=sessions_dir):
            # Need to patch the sessions_dir path
            pass
        # Direct test with patching
        msgs = _read_recent_messages("nonexistent-session-id")
        assert msgs == []

    def test_reads_user_and_assistant_messages(self, sessions_dir):
        entries = [
            {"role": "user", "content": "Hello, how are you?"},
            {"role": "assistant", "content": "I'm doing great!"},
            {"role": "user", "content": "Tell me about Python."},
            {"role": "assistant", "content": "Python is a great language."},
        ]
        session_id = "test-session-1"
        _create_session_jsonl(sessions_dir, session_id, entries)

        with patch("api.services.memory_archiver.os.path.expanduser", return_value=sessions_dir):
            msgs = _read_recent_messages(session_id)

        assert len(msgs) == 4
        assert msgs[0]["role"] == "user"
        assert msgs[0]["text"] == "Hello, how are you?"

    def test_skips_metadata_entries(self, sessions_dir):
        entries = [
            {"type": "metadata", "model": "claude-3"},
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "content": "Hello"},
        ]
        session_id = "test-meta"
        _create_session_jsonl(sessions_dir, session_id, entries)

        with patch("api.services.memory_archiver.os.path.expanduser", return_value=sessions_dir):
            msgs = _read_recent_messages(session_id)

        assert len(msgs) == 2

    def test_skips_system_role(self, sessions_dir):
        entries = [
            {"role": "system", "content": "You are a helpful assistant"},
            {"role": "user", "content": "Hi"},
        ]
        session_id = "test-system"
        _create_session_jsonl(sessions_dir, session_id, entries)

        with patch("api.services.memory_archiver.os.path.expanduser", return_value=sessions_dir):
            msgs = _read_recent_messages(session_id)

        assert len(msgs) == 1
        assert msgs[0]["role"] == "user"

    def test_skips_slash_commands(self, sessions_dir):
        entries = [
            {"role": "user", "content": "/help"},
            {"role": "user", "content": "Real question"},
        ]
        session_id = "test-slash"
        _create_session_jsonl(sessions_dir, session_id, entries)

        with patch("api.services.memory_archiver.os.path.expanduser", return_value=sessions_dir):
            msgs = _read_recent_messages(session_id)

        assert len(msgs) == 1
        assert msgs[0]["text"] == "Real question"

    def test_handles_content_array(self, sessions_dir):
        entries = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Part 1"},
                    {"type": "image", "source": "..."},
                    {"type": "text", "text": "Part 2"},
                ],
            },
        ]
        session_id = "test-array"
        _create_session_jsonl(sessions_dir, session_id, entries)

        with patch("api.services.memory_archiver.os.path.expanduser", return_value=sessions_dir):
            msgs = _read_recent_messages(session_id)

        assert len(msgs) == 1
        assert "Part 1" in msgs[0]["text"]
        assert "Part 2" in msgs[0]["text"]

    def test_respects_message_count_limit(self, sessions_dir):
        entries = [{"role": "user", "content": f"Message {i}"} for i in range(20)]
        session_id = "test-limit"
        _create_session_jsonl(sessions_dir, session_id, entries)

        with patch("api.services.memory_archiver.os.path.expanduser", return_value=sessions_dir):
            msgs = _read_recent_messages(session_id, message_count=5)

        assert len(msgs) == 5
        # Should be the last 5 messages
        assert msgs[0]["text"] == "Message 15"
        assert msgs[4]["text"] == "Message 19"

    def test_handles_malformed_jsonl(self, sessions_dir):
        session_id = "test-malformed"
        session_dir = os.path.join(sessions_dir, session_id)
        os.makedirs(session_dir, exist_ok=True)
        jsonl_path = os.path.join(session_dir, f"{session_id}.jsonl")
        with open(jsonl_path, "w") as f:
            f.write("not valid json\n")
            f.write(json.dumps({"role": "user", "content": "valid"}) + "\n")
            f.write("{broken\n")

        with patch("api.services.memory_archiver.os.path.expanduser", return_value=sessions_dir):
            msgs = _read_recent_messages(session_id)

        assert len(msgs) == 1
        assert msgs[0]["text"] == "valid"


class TestGenerateSlug:
    """Test _generate_slug function."""

    def test_extracts_key_words(self):
        messages = [{"role": "user", "text": "How do I implement a binary search tree in Python?"}]
        slug = _generate_slug(messages)
        assert len(slug) > 0
        assert "-" in slug or len(slug.split("-")) >= 1

    def test_skips_stop_words(self):
        messages = [{"role": "user", "text": "What is the best way to do this thing?"}]
        slug = _generate_slug(messages)
        # "what", "is", "the", "to", "do", "this" are all stop words
        assert "what" not in slug.split("-")
        assert "the" not in slug.split("-")

    def test_uses_first_substantive_message(self):
        messages = [
            {"role": "user", "text": "hi"},  # too short (<= 10 chars)
            {"role": "user", "text": "Can you help me debug my Python FastAPI application?"},
        ]
        slug = _generate_slug(messages)
        assert "python" in slug or "fastapi" in slug or "debug" in slug or "application" in slug

    def test_fallback_to_timestamp(self):
        messages = [{"role": "assistant", "text": "Hello there!"}]
        slug = _generate_slug(messages)
        # Should be a 4-digit time string (HHMM)
        assert len(slug) == 4
        assert slug.isdigit()

    def test_limits_to_4_words(self):
        messages = [{"role": "user", "text": "implement binary search tree algorithm data structure optimization performance"}]
        slug = _generate_slug(messages)
        parts = slug.split("-")
        assert len(parts) <= 4

    def test_handles_chinese_text(self):
        messages = [{"role": "user", "text": "请帮我实现一个记忆系统的搜索功能"}]
        slug = _generate_slug(messages)
        assert len(slug) > 0


class TestFormatArchive:
    """Test _format_archive function."""

    def test_contains_session_metadata(self):
        messages = [{"role": "user", "text": "Hello"}]
        content = _format_archive("session-123", messages, "test-slug")
        assert "session-123" in content
        assert "test slug" in content  # slug with dashes replaced by spaces

    def test_contains_message_count(self):
        messages = [
            {"role": "user", "text": "Q1"},
            {"role": "assistant", "text": "A1"},
        ]
        content = _format_archive("s1", messages, "slug")
        assert "**Messages**: 2" in content

    def test_formats_user_and_assistant(self):
        messages = [
            {"role": "user", "text": "What is Python?"},
            {"role": "assistant", "text": "Python is a programming language."},
        ]
        content = _format_archive("s1", messages, "python")
        assert "**User**: What is Python?" in content
        assert "**Assistant**: Python is a programming language." in content

    def test_truncates_long_messages(self):
        messages = [{"role": "user", "text": "x" * 3000}]
        content = _format_archive("s1", messages, "long")
        assert "... (truncated)" in content
        # The truncated text should be around 2000 chars, not 3000
        user_line = [l for l in content.split("\n") if l.startswith("**User**:")][0]
        assert len(user_line) < 2100

    def test_has_markdown_structure(self):
        messages = [{"role": "user", "text": "Hello"}]
        content = _format_archive("s1", messages, "test")
        assert content.startswith("# Session Archive:")
        assert "## Conversation" in content


class TestArchiveSession:
    """Test the async archive_session entry point."""

    @pytest.mark.asyncio
    async def test_disabled_by_config(self):
        config = {"local_memory_enabled": False}
        with patch("api.services.memory_sync.load_memory_config", return_value=config):
            result = await archive_session("session-1")
        assert result["archived"] is False
        assert result["reason"] == "local_memory_disabled"

    @pytest.mark.asyncio
    async def test_auto_archive_disabled(self):
        config = {"local_memory_enabled": True, "auto_archive_on_reset": False}
        with patch("api.services.memory_sync.load_memory_config", return_value=config):
            result = await archive_session("session-1")
        assert result["archived"] is False
        assert result["reason"] == "auto_archive_disabled"

    @pytest.mark.asyncio
    async def test_no_manager_returns_error(self):
        config = {"local_memory_enabled": True, "auto_archive_on_reset": True}
        with patch("api.services.memory_sync.load_memory_config", return_value=config), \
             patch("api.services.memory_files.get_memory_file_manager", return_value=None):
            result = await archive_session("session-1")
        assert result["archived"] is False
        assert result["reason"] == "memory_file_manager_not_initialized"

    @pytest.mark.asyncio
    async def test_no_messages_returns_early(self):
        config = {"local_memory_enabled": True, "auto_archive_on_reset": True}
        mock_mgr = MagicMock()
        with patch("api.services.memory_sync.load_memory_config", return_value=config), \
             patch("api.services.memory_files.get_memory_file_manager", return_value=mock_mgr), \
             patch("api.services.memory_archiver._read_recent_messages", return_value=[]):
            result = await archive_session("empty-session")
        assert result["archived"] is False
        assert result["reason"] == "no_messages"

    @pytest.mark.asyncio
    async def test_successful_archive(self):
        config = {"local_memory_enabled": True, "auto_archive_on_reset": True}
        mock_mgr = MagicMock()
        mock_mgr.write_session_archive.return_value = "/fake/workspace/memory/2026-02-26-test.md"
        mock_mgr.workspace_dir = "/fake/workspace"

        messages = [
            {"role": "user", "text": "How do I test Python code?"},
            {"role": "assistant", "text": "Use pytest."},
        ]

        with patch("api.services.memory_sync.load_memory_config", return_value=config), \
             patch("api.services.memory_files.get_memory_file_manager", return_value=mock_mgr), \
             patch("api.services.memory_archiver._read_recent_messages", return_value=messages):
            result = await archive_session("test-session")

        assert result["archived"] is True
        assert result["message_count"] == 2
        assert result["session_id"] == "test-session"
        mock_mgr.write_session_archive.assert_called_once()

    @pytest.mark.asyncio
    async def test_write_error_handled(self):
        config = {"local_memory_enabled": True, "auto_archive_on_reset": True}
        mock_mgr = MagicMock()
        mock_mgr.write_session_archive.side_effect = IOError("disk full")
        mock_mgr.workspace_dir = "/fake/workspace"

        messages = [{"role": "user", "text": "test message for archive"}]

        with patch("api.services.memory_sync.load_memory_config", return_value=config), \
             patch("api.services.memory_files.get_memory_file_manager", return_value=mock_mgr), \
             patch("api.services.memory_archiver._read_recent_messages", return_value=messages):
            result = await archive_session("test-session")

        assert result["archived"] is False
        assert "disk full" in result["error"]
