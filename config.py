"""
Springo Backend Configuration
Centralized timeout and limit settings
"""

# =============================================================================
# Timeout Configuration (in seconds)
# =============================================================================

class TimeoutConfig:
    """Timeout settings for various operations"""

    # Bedrock API
    BEDROCK_CONNECT = 60          # Connection timeout
    BEDROCK_READ = 900            # Read timeout (15 min for long conversations)

    # Tool Execution
    COMMAND_DEFAULT = 300         # Default command execution (5 min)
    COMMAND_QUICK = 30            # Quick commands (file ops, etc.)
    COMMAND_LONG = 600            # Long running commands (builds, etc.)

    # External Services
    HTTP_REQUEST = 60             # HTTP requests to external APIs
    MCP_TOOL = 120                # MCP tool calls

    # SSE Streaming
    SSE_HEARTBEAT_INTERVAL = 10   # Heartbeat interval to keep connection alive

    # Background Tasks
    BACKGROUND_TASK_MAX = 3600    # Max time for background tasks (1 hour)


class LimitConfig:
    """Limit settings for resource management"""

    # Parallel Execution
    MAX_PARALLEL_TOOLS = 10       # Max concurrent tool executions

    # Output Size
    MAX_INLINE_OUTPUT = 30000     # Max bytes for inline tool output (30KB)
    MAX_TOOL_OUTPUT = 1000000     # Max bytes for tool output file (1MB)

    # Context
    MAX_CONTEXT_TOKENS = 200000   # Claude context window
    COMPACT_THRESHOLD = 120000    # Trigger compaction at 60%


# Singleton instances
TIMEOUTS = TimeoutConfig()
LIMITS = LimitConfig()
