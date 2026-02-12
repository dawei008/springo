"""
Springo Agent Teams Models
多 Agent 团队协作模型定义
"""
import uuid
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Literal
from datetime import datetime

# Module-level constants for team model defaults.
# Empty string means "inherit from user's request.model" (which defaults to
# the main agent's active model).  Only set a concrete value here if you want
# a hard-coded fallback when the request doesn't specify a model.
DEFAULT_TEAM_SMART_MODEL = ""
DEFAULT_TEAM_FAST_MODEL = ""


class AgentRole(BaseModel):
    """Agent 角色定义"""
    name: str = Field(..., description="Role name (orchestrator, explorer, researcher, implementer, reviewer)")
    system_prompt: str = Field(default="", description="Role-specific system prompt")
    model: str = Field(default=DEFAULT_TEAM_FAST_MODEL, description="Model to use for this role")
    tools_available: List[str] = Field(default_factory=list, description="Tool names this role can access")
    purpose: str = Field(default="", description="Brief description of role purpose")


class TeamAgent(BaseModel):
    """团队中的单个 Agent"""
    agent_id: str = Field(default_factory=lambda: f"agent_{uuid.uuid4().hex[:8]}")
    name: str = Field(default="", description="Human-readable agent name (e.g., 'researcher-1')")
    role: AgentRole
    custom_instructions: str = Field(default="", description="Custom instructions from orchestrator for this agent")
    status: Literal["idle", "thinking", "executing", "complete", "error"] = "idle"
    findings: str = ""
    assigned_task: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    token_usage: Dict[str, int] = Field(default_factory=lambda: {"input_tokens": 0, "output_tokens": 0})


class TaskBoardItem(BaseModel):
    """任务板条目"""
    task_id: str = Field(default_factory=lambda: f"task_{uuid.uuid4().hex[:8]}")
    title: str
    description: str
    assigned_to: Optional[str] = None
    status: Literal["pending", "in_progress", "complete", "error"] = "pending"
    findings: str = ""
    dependencies: List[str] = Field(default_factory=list, description="Task IDs this depends on")


class EnhancedTaskBoardItem(BaseModel):
    """Enhanced task board item for collaborative mode with dependency tracking"""
    task_id: str = Field(default_factory=lambda: f"task_{uuid.uuid4().hex[:8]}")
    title: str = ""
    description: str = ""
    owner: Optional[str] = Field(default=None, description="Agent name who owns this task")
    status: Literal["pending", "in_progress", "completed", "error"] = "pending"
    active_form: str = Field(default="", description="Present continuous form shown in spinner (e.g., 'Running tests')")
    blocks: List[str] = Field(default_factory=list, description="Task IDs that this task blocks")
    blocked_by: List[str] = Field(default_factory=list, description="Task IDs that must complete before this one")
    findings: str = ""


class Team(BaseModel):
    """Agent 团队"""
    team_id: str = Field(default_factory=lambda: f"team_{uuid.uuid4().hex[:12]}")
    execution_mode: Literal["classic", "collaborative"] = Field(
        default="classic", description="Team execution mode"
    )
    agents: List[TeamAgent] = Field(default_factory=list)
    task_board: List[TaskBoardItem] = Field(default_factory=list)
    status: Literal["created", "planning", "executing", "synthesizing", "complete", "error"] = "created"
    shared_context: str = ""
    user_request: str = ""
    final_result: str = ""
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    completed_at: Optional[str] = None
    total_tokens: Dict[str, int] = Field(default_factory=lambda: {"input_tokens": 0, "output_tokens": 0})


class TeamSpawnRequest(BaseModel):
    """创建团队请求"""
    user_request: str = Field(..., description="The user's request to decompose into agent tasks")
    model: str = Field(default="", description="Model for all team agents (empty = use main agent's active model)")
    context: Optional[str] = Field(default=None, description="Additional context for the team")
    mode: Literal["classic", "collaborative"] = Field(
        default="classic", description="Team execution mode: classic (one-shot parallel) or collaborative (long-lived agents)"
    )


class TeamExecuteRequest(BaseModel):
    """执行团队请求"""
    stream: bool = Field(default=True, description="Enable SSE streaming for progress")


# Pre-defined role configurations
ROLE_CONFIGS = {
    "orchestrator": AgentRole(
        name="orchestrator",
        model=DEFAULT_TEAM_SMART_MODEL,
        purpose="Dynamic task decomposition and result synthesis",
        system_prompt=(
            "You are the orchestrator agent. Your job is to:\n"
            "1. Analyze the user's request and judge its complexity\n"
            "2. Decompose it into 1-10 subtasks (simple questions may need only 1 agent)\n"
            "3. Assign roles to each subtask - use built-in roles or create custom ones\n"
            "4. Synthesize findings from all agents into a coherent response\n\n"
            "Built-in roles: explorer, researcher, implementer, reviewer\n"
            "You may also create custom role names with custom_instructions.\n\n"
            "When decomposing tasks, output a JSON array of subtasks:\n"
            '[\n'
            '  {"title": "...", "description": "...", "role": "...", "custom_instructions": "(optional)"}\n'
            ']\n\n'
            "When synthesizing, combine all agent findings into a clear, complete response.\n"
            "Do NOT use emojis. Use plain text only."
        ),
    ),
    "explorer": AgentRole(
        name="explorer",
        model=DEFAULT_TEAM_FAST_MODEL,
        purpose="Code and data exploration",
        system_prompt=(
            "You are an explorer agent. Your job is to explore code, data, and files to find relevant information.\n"
            "You have access to tools: use read_file, glob, grep, execute_command, etc. to explore the codebase.\n"
            "ALWAYS use tools to gather real information — do NOT guess or hallucinate file contents.\n"
            "Be thorough but concise in your findings. Report what you found clearly.\n"
            "Do NOT use emojis. Use plain text only."
        ),
    ),
    "researcher": AgentRole(
        name="researcher",
        model=DEFAULT_TEAM_FAST_MODEL,
        purpose="Web search and documentation research",
        system_prompt=(
            "You are a researcher agent. Your job is to find information using available tools.\n"
            "Use web search tools (web-search__brave_web_search, web-search__brave_news_search, etc.) "
            "to find up-to-date information. Use tool_search to discover available tools.\n"
            "ALWAYS use tools to search — do NOT make up information.\n"
            "Provide well-organized findings with sources when available.\n"
            "Do NOT use emojis. Use plain text only."
        ),
    ),
    "implementer": AgentRole(
        name="implementer",
        model=DEFAULT_TEAM_SMART_MODEL,
        purpose="Code writing and implementation",
        system_prompt=(
            "You are an implementer agent. Your job is to write code, create implementations, and make changes.\n"
            "You have access to tools: use write_file, read_file, execute_command, etc. to implement code.\n"
            "ALWAYS use tools to read existing code before modifying it.\n"
            "Follow existing code patterns. Be precise and test-aware.\n"
            "Do NOT use emojis. Use plain text only."
        ),
    ),
    "reviewer": AgentRole(
        name="reviewer",
        model=DEFAULT_TEAM_FAST_MODEL,
        purpose="Quality review and verification",
        system_prompt=(
            "You are a reviewer agent. Your job is to review code, findings, and implementations for quality.\n"
            "Use tools (read_file, grep, execute_command) to verify claims and check code.\n"
            "Look for issues, suggest improvements, and verify correctness.\n"
            "Do NOT use emojis. Use plain text only."
        ),
    ),
}
