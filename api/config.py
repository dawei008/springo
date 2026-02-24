"""
Springo FastAPI Configuration Module
使用 Pydantic Settings 进行配置管理
"""
from pydantic_settings import BaseSettings
from pydantic import Field
from functools import lru_cache
from pathlib import Path
import os


class Settings(BaseSettings):
    """应用配置"""
    
    # AWS Configuration
    aws_region: str = Field(default="us-west-2", description="AWS Region")
    bedrock_model_id: str = Field(
        default="us.anthropic.claude-sonnet-4-5-20250929-v1:0",
        description="Default Bedrock Model ID"
    )
    compact_model_id: str = Field(
        default="claude-haiku-4-5-20251001",
        description="Model for context compaction"
    )
    nl_parse_model_id: str = Field(
        default="claude-haiku-4-5-20251001",
        description="Model for natural language to command parsing"
    )
    news_format_model_id: str = Field(
        default="claude-sonnet-4-5-20250929",
        description="Model for news formatting"
    )
    default_chat_model: str = Field(
        default="claude-opus-4-6",
        description="Default chat model for new sessions"
    )

    # DeepSeek Direct API
    deepseek_api_key: str = Field(default="", description="DeepSeek API key")
    deepseek_base_url: str = Field(default="https://api.deepseek.com", description="DeepSeek API base URL")

    # Server Configuration
    host: str = Field(default="0.0.0.0", description="Server host")
    port: int = Field(default=8081, description="Server port")
    debug: bool = Field(default=True, description="Debug mode")
    
    # Paths
    springo_config_dir: str = Field(
        default="~/.springo",
        description="Springo config directory"
    )
    session_storage_dir: str = Field(
        default="~/.springo/sessions",
        description="Session storage directory"
    )
    
    # MCP Configuration
    mcp_config_path: str = Field(
        default="~/.springo/mcp_servers.json",
        description="MCP servers config file path"
    )
    
    # Timeouts (seconds)
    bedrock_connect_timeout: int = Field(default=60, description="Bedrock connection timeout")
    bedrock_read_timeout: int = Field(default=900, description="Bedrock read timeout (15min for long conversations)")
    bedrock_stream_chunk_timeout: int = Field(default=300, description="Timeout for individual stream chunks (5min; Opus extended thinking needs longer)")
    tool_execution_timeout: int = Field(default=300, description="Default tool/command execution timeout")
    tool_execution_timeout_quick: int = Field(default=30, description="Quick tool execution (file ops, etc.)")
    tool_execution_timeout_long: int = Field(default=600, description="Long tool execution (builds, installs)")
    mcp_tool_timeout: int = Field(default=120, description="MCP external tool call timeout")
    http_request_timeout: int = Field(default=60, description="HTTP requests to external APIs")
    sse_heartbeat_interval: int = Field(default=10, description="SSE heartbeat interval to keep connection alive")
    background_task_max_timeout: int = Field(default=3600, description="Max time for background tasks (1 hour)")

    # Limits
    max_tool_iterations: int = Field(default=1000, description="Max auto tool loop iterations (safety cap)")
    max_parallel_tools: int = Field(default=10, description="Max parallel tool executions")
    max_inline_output: int = Field(default=30000, description="Max bytes for inline tool output (30KB)")
    max_tool_output: int = Field(default=1000000, description="Max bytes for tool output file (1MB)")
    max_context_tokens: int = Field(default=200000, description="Max context window tokens (200K)")
    compact_threshold: int = Field(default=120000, description="Token threshold to trigger context compaction")

    # Feishu Integration
    feishu_enabled: bool = Field(default=False, description="Enable Feishu bot integration")
    feishu_app_id: str = Field(default="", description="Feishu app ID")
    feishu_app_secret: str = Field(default="", description="Feishu app secret")

    # Agent Teams — Collaborative mode limits
    team_agent_wall_clock_timeout: int = Field(
        default=1800, description="Max wall-clock seconds per agent (default 30min)")
    team_agent_max_messages: int = Field(
        default=100, description="Max messages an agent can process before stopping")
    team_agent_max_tool_iterations: int = Field(
        default=30, description="Max tool iterations per message turn for team agents")
    team_collab_max_runtime: int = Field(
        default=3600, description="Max wall-clock seconds for collaborative team execution (default 1h)")
    team_idle_timeout: int = Field(
        default=120, description="Seconds of idle before agent self-terminates (2 min)")
    team_max_concurrent_teams: int = Field(
        default=5, description="Max simultaneously active teams")
    team_completed_cleanup_secs: int = Field(
        default=3600, description="Seconds after completion before team memory is freed (1h)")
    team_msg_max_inline_size: int = Field(
        default=16384, description="Max chars for inline message; larger content offloaded to file")
    team_message_log_max: int = Field(
        default=500, description="Max messages kept in message bus log (rolling window)")
    team_event_queue_max: int = Field(
        default=5000, description="Max SSE events buffered in event queue")
    team_storage_dir: str = Field(
        default="~/.springo/teams",
        description="Directory for team state file persistence"
    )
    team_bedrock_max_retries: int = Field(
        default=3, description="Max retries for transient Bedrock API errors")
    team_bedrock_retry_base_delay: float = Field(
        default=1.0, description="Base delay in seconds for Bedrock retry backoff")
    
    model_config = {
        "env_prefix": "SPRINGO_",
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore"
    }
    
    @property
    def springo_config_path(self) -> Path:
        """Get expanded springo config directory path"""
        return Path(os.path.expanduser(self.springo_config_dir))
    
    @property
    def session_storage_path(self) -> Path:
        """Get expanded session storage path"""
        return Path(os.path.expanduser(self.session_storage_dir))
    
    @property
    def team_storage_path(self) -> Path:
        """Get expanded team storage directory path"""
        return Path(os.path.expanduser(self.team_storage_dir))

    @property
    def mcp_config_file_path(self) -> Path:
        """Get expanded MCP config file path"""
        return Path(os.path.expanduser(self.mcp_config_path))


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance"""
    return Settings()


# Convenience function
settings = get_settings()
