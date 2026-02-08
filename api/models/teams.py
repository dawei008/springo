"""
Springo Agent Teams Models
多 Agent 团队协作模型定义
"""
import uuid
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any, Literal
from datetime import datetime


class AgentRole(BaseModel):
    """Agent 角色定义"""
    name: str = Field(..., description="Role name (orchestrator, explorer, researcher, implementer, reviewer)")
    system_prompt: str = Field(default="", description="Role-specific system prompt")
    model: str = Field(default="claude-haiku-4-5-20251001", description="Model to use for this role")
    tools_available: List[str] = Field(default_factory=list, description="Tool names this role can access")
    purpose: str = Field(default="", description="Brief description of role purpose")


class TeamAgent(BaseModel):
    """团队中的单个 Agent"""
    agent_id: str = Field(default_factory=lambda: f"agent_{uuid.uuid4().hex[:8]}")
    role: AgentRole
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


class Team(BaseModel):
    """Agent 团队"""
    team_id: str = Field(default_factory=lambda: f"team_{uuid.uuid4().hex[:12]}")
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
    max_parallel_agents: int = Field(default=3, ge=1, le=5, description="Max agents to run in parallel")
    model: str = Field(default="claude-sonnet-4-5-20250929", description="Orchestrator model")
    context: Optional[str] = Field(default=None, description="Additional context for the team")


class TeamExecuteRequest(BaseModel):
    """执行团队请求"""
    stream: bool = Field(default=True, description="Enable SSE streaming for progress")


# Pre-defined role configurations
ROLE_CONFIGS = {
    "orchestrator": AgentRole(
        name="orchestrator",
        model="claude-sonnet-4-5-20250929",
        purpose="Task decomposition and result synthesis",
        system_prompt=(
            "You are the orchestrator agent. Your job is to:\n"
            "1. Analyze the user's request\n"
            "2. Decompose it into specific subtasks\n"
            "3. Assign roles to each subtask\n"
            "4. Synthesize findings from all agents into a coherent response\n\n"
            "When decomposing tasks, output a JSON array of subtasks:\n"
            '[\n'
            '  {"title": "...", "description": "...", "role": "explorer|researcher|implementer|reviewer"}\n'
            ']\n\n'
            "When synthesizing, combine all agent findings into a clear, complete response.\n"
            "Do NOT use emojis. Use plain text only."
        ),
    ),
    "explorer": AgentRole(
        name="explorer",
        model="claude-haiku-4-5-20251001",
        purpose="Code and data exploration",
        system_prompt=(
            "You are an explorer agent. Your job is to explore code, data, and files to find relevant information.\n"
            "Be thorough but concise in your findings. Report what you found clearly.\n"
            "Do NOT use emojis. Use plain text only."
        ),
    ),
    "researcher": AgentRole(
        name="researcher",
        model="claude-haiku-4-5-20251001",
        purpose="Web search and documentation research",
        system_prompt=(
            "You are a researcher agent. Your job is to find information from documentation, web search results, and reference materials.\n"
            "Provide well-organized findings with sources when available.\n"
            "Do NOT use emojis. Use plain text only."
        ),
    ),
    "implementer": AgentRole(
        name="implementer",
        model="claude-sonnet-4-5-20250929",
        purpose="Code writing and implementation",
        system_prompt=(
            "You are an implementer agent. Your job is to write code, create implementations, and make changes.\n"
            "Follow existing code patterns. Be precise and test-aware.\n"
            "Do NOT use emojis. Use plain text only."
        ),
    ),
    "reviewer": AgentRole(
        name="reviewer",
        model="claude-haiku-4-5-20251001",
        purpose="Quality review and verification",
        system_prompt=(
            "You are a reviewer agent. Your job is to review code, findings, and implementations for quality.\n"
            "Look for issues, suggest improvements, and verify correctness.\n"
            "Do NOT use emojis. Use plain text only."
        ),
    ),
}
