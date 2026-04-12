"""
Springo API Response Models
API 响应模型定义
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any, Union, Literal
from datetime import datetime


class Usage(BaseModel):
    """Token 使用统计"""
    input_tokens: int = 0
    output_tokens: int = 0


class TextBlock(BaseModel):
    """文本内容块"""
    type: Literal["text"] = "text"
    text: str


class ToolUseBlock(BaseModel):
    """工具调用块"""
    type: Literal["tool_use"] = "tool_use"
    id: str
    name: str
    input: Dict[str, Any]


ContentBlock = Union[TextBlock, ToolUseBlock]


class MessageResponse(BaseModel):
    """消息响应模型 - 兼容 Anthropic API 格式"""
    id: str = Field(..., description="Message ID")
    type: Literal["message"] = "message"
    role: Literal["assistant"] = "assistant"
    content: List[ContentBlock] = Field(default_factory=list)
    model: str
    stop_reason: Optional[str] = None
    stop_sequence: Optional[str] = None
    usage: Usage = Field(default_factory=Usage)


class ErrorDetail(BaseModel):
    """错误详情"""
    type: str = "error"
    message: str
    code: Optional[str] = None
    details: Optional[Dict[str, Any]] = None


class ErrorResponse(BaseModel):
    """错误响应"""
    type: Literal["error"] = "error"
    error: ErrorDetail


class ToolResult(BaseModel):
    """工具执行结果"""
    tool_use_id: str
    tool_name: str
    result: Any
    is_error: bool = False
    elapsed: Optional[float] = None


class ToolExecuteResponse(BaseModel):
    """工具执行响应"""
    success: bool
    results: List[ToolResult] = Field(default_factory=list)
    error: Optional[str] = None


class HealthResponse(BaseModel):
    """健康检查响应"""
    status: str = "healthy"
    version: str = "2.0.0"
    framework: str = "FastAPI"
    model: str
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())


# SSE Event Models
class SSEMessageStart(BaseModel):
    """SSE message_start 事件"""
    type: Literal["message_start"] = "message_start"
    message: Dict[str, Any]


class SSEContentBlockStart(BaseModel):
    """SSE content_block_start 事件"""
    type: Literal["content_block_start"] = "content_block_start"
    index: int
    content_block: Dict[str, Any]


class SSEContentBlockDelta(BaseModel):
    """SSE content_block_delta 事件"""
    type: Literal["content_block_delta"] = "content_block_delta"
    index: int
    delta: Dict[str, Any]


class SSEContentBlockStop(BaseModel):
    """SSE content_block_stop 事件"""
    type: Literal["content_block_stop"] = "content_block_stop"
    index: int


class SSEMessageDelta(BaseModel):
    """SSE message_delta 事件"""
    type: Literal["message_delta"] = "message_delta"
    delta: Dict[str, Any]
    usage: Dict[str, int]


class SSEMessageStop(BaseModel):
    """SSE message_stop 事件"""
    type: Literal["message_stop"] = "message_stop"


class SSEError(BaseModel):
    """SSE error 事件"""
    type: Literal["error"] = "error"
    error: ErrorDetail


# Tool execution SSE events
class SSEToolStart(BaseModel):
    """SSE tool_start 事件"""
    type: Literal["tool_start"] = "tool_start"
    tool_use_id: str
    tool_name: str


class SSEToolHeartbeat(BaseModel):
    """SSE heartbeat 事件 (工具执行期间)"""
    type: Literal["heartbeat"] = "heartbeat"
    tool_use_id: Optional[str] = None
    elapsed: float


class SSEToolResult(BaseModel):
    """SSE tool_result 事件"""
    type: Literal["tool_result"] = "tool_result"
    tool_use_id: str
    tool_name: str
    result: Any
    is_error: bool = False
    elapsed: float


# Plan Mode Models
class PlanStep(BaseModel):
    """计划步骤"""
    description: str
    tool_name: Optional[str] = None
    tool_input: Optional[Dict[str, Any]] = None


class PlanSection(BaseModel):
    """计划段落"""
    id: str
    title: str
    description: str
    steps: List[str] = Field(default_factory=list)
    status: Literal["pending", "approved", "rejected", "in_progress", "completed", "failed"] = "pending"
    feedback: Optional[str] = None
    result: Optional[str] = None


class PlanStructure(BaseModel):
    """完整计划"""
    id: str
    title: str
    summary: str
    sections: List[PlanSection] = Field(default_factory=list)
    status: Literal["draft", "reviewing", "approved", "executing", "completed", "failed"] = "draft"
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    session_id: Optional[str] = None


class SessionInfo(BaseModel):
    """会话信息"""
    id: str
    name: Optional[str] = None
    created_at: str
    updated_at: str
    message_count: int = 0
    working_directory: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class SessionListResponse(BaseModel):
    """会话列表响应"""
    sessions: List[SessionInfo]
    total: int
