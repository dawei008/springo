"""
Unit tests for memory_archiver (api/services/memory_archiver.py)

Tests cover:
- Reading recent messages from JSONL session files
- Fact extraction archive_session flow (model call + daily log write)
"""
import json
import os
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from datetime import datetime

from api.services.memory_archiver import (
    _read_recent_messages,
    _build_messages_text,
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


class TestBuildMessagesText:
    """Test _build_messages_text helper."""

    def test_builds_text_from_messages(self):
        messages = [
            {"role": "user", "text": "Hello world"},
            {"role": "assistant", "text": "Hi there"},
        ]
        text = _build_messages_text(messages)
        assert "[user]: Hello world" in text
        assert "[assistant]: Hi there" in text

    def test_truncates_long_messages(self):
        messages = [{"role": "user", "text": "x" * 1000}]
        text = _build_messages_text(messages)
        # Each message snippet is capped at 500 chars
        assert len(text) < 600

    def test_respects_max_chars(self):
        messages = [{"role": "user", "text": f"Message {i} " * 50} for i in range(20)]
        text = _build_messages_text(messages, max_chars=500)
        assert len(text) <= 600  # Some tolerance for the last line

    def test_empty_messages(self):
        text = _build_messages_text([])
        assert text == ""


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
    async def test_nothing_to_remember(self):
        """Model returns NOTHING_TO_REMEMBER for trivial conversations."""
        config = {"local_memory_enabled": True, "auto_archive_on_reset": True}
        mock_mgr = MagicMock()
        messages = [
            {"role": "user", "text": "hi"},
            {"role": "assistant", "text": "Hello!"},
        ]

        # Mock bedrock to return NOTHING_TO_REMEMBER
        mock_bedrock = AsyncMock()
        mock_bedrock.invoke_model.return_value = {
            "content": [{"type": "text", "text": "NOTHING_TO_REMEMBER"}]
        }

        with patch("api.services.memory_sync.load_memory_config", return_value=config), \
             patch("api.services.memory_files.get_memory_file_manager", return_value=mock_mgr), \
             patch("api.services.memory_archiver._read_recent_messages", return_value=messages), \
             patch("api.services.bedrock.get_bedrock_service", return_value=mock_bedrock), \
             patch("api.config.get_settings") as mock_settings, \
             patch("api.services.model_registry.get_model_info", return_value={"api_format": "anthropic"}), \
             patch("api.services.model_registry.get_bedrock_id", return_value="us.anthropic.claude-haiku"):
            mock_settings.return_value.compact_model_id = "claude-haiku-4-5-20251001"
            result = await archive_session("trivial-session")

        assert result["archived"] is False
        assert result["reason"] == "nothing_to_remember"

    @pytest.mark.asyncio
    async def test_successful_fact_extraction(self):
        """Model extracts facts and writes to daily log."""
        config = {"local_memory_enabled": True, "auto_archive_on_reset": True}
        mock_mgr = MagicMock()
        messages = [
            {"role": "user", "text": "I prefer dark mode and use Python with FastAPI."},
            {"role": "assistant", "text": "I'll remember your preferences."},
        ]

        extracted_facts = "- [preference] User prefers dark mode\n- [context] Project uses Python + FastAPI"
        mock_bedrock = AsyncMock()
        mock_bedrock.invoke_model.return_value = {
            "content": [{"type": "text", "text": extracted_facts}]
        }

        mock_write_result = {"success": True, "path": "memory/2026-02-27.md", "target": "daily"}

        with patch("api.services.memory_sync.load_memory_config", return_value=config), \
             patch("api.services.memory_files.get_memory_file_manager", return_value=mock_mgr), \
             patch("api.services.memory_archiver._read_recent_messages", return_value=messages), \
             patch("api.services.bedrock.get_bedrock_service", return_value=mock_bedrock), \
             patch("api.config.get_settings") as mock_settings, \
             patch("api.services.model_registry.get_model_info", return_value={"api_format": "anthropic"}), \
             patch("api.services.model_registry.get_bedrock_id", return_value="us.anthropic.claude-haiku"), \
             patch("mcp_tools.handlers.memory_tools.memory_write", return_value=mock_write_result):
            mock_settings.return_value.compact_model_id = "claude-haiku-4-5-20251001"
            result = await archive_session("test-session")

        assert result["archived"] is True
        assert result["facts_count"] == 2
        assert result["message_count"] == 2

    @pytest.mark.asyncio
    async def test_model_error_handled(self):
        """If Bedrock call fails, archive returns error gracefully."""
        config = {"local_memory_enabled": True, "auto_archive_on_reset": True}
        mock_mgr = MagicMock()
        messages = [{"role": "user", "text": "test message"}]

        mock_bedrock = AsyncMock()
        mock_bedrock.invoke_model.side_effect = Exception("Bedrock timeout")

        with patch("api.services.memory_sync.load_memory_config", return_value=config), \
             patch("api.services.memory_files.get_memory_file_manager", return_value=mock_mgr), \
             patch("api.services.memory_archiver._read_recent_messages", return_value=messages), \
             patch("api.services.bedrock.get_bedrock_service", return_value=mock_bedrock), \
             patch("api.config.get_settings") as mock_settings, \
             patch("api.services.model_registry.get_model_info", return_value={"api_format": "anthropic"}), \
             patch("api.services.model_registry.get_bedrock_id", return_value="us.anthropic.claude-haiku"):
            mock_settings.return_value.compact_model_id = "claude-haiku-4-5-20251001"
            result = await archive_session("error-session")

        assert result["archived"] is False
        assert "Bedrock timeout" in result["error"]
