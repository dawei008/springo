"""
Springo API Request Models
API 请求模型定义
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any, Union, Literal


class TextContent(BaseModel):
    """文本内容"""
    type: Literal["text"] = "text"
    text: str


class ImageSource(BaseModel):
    """图片来源"""
    type: Literal["base64"] = "base64"
    media_type: str = Field(..., description="Image MIME type")
    data: str = Field(..., description="Base64 encoded image data")


class ImageContent(BaseModel):
    """图片内容"""
    type: Literal["image"] = "image"
    source: ImageSource


class ToolUseContent(BaseModel):
    """工具调用内容"""
    type: Literal["tool_use"] = "tool_use"
    id: str
    name: str
    input: Dict[str, Any]


class ToolResultContent(BaseModel):
    """工具结果内容"""
    type: Literal["tool_result"] = "tool_result"
    tool_use_id: str
    content: Union[str, List[Dict[str, Any]]]
    is_error: bool = False


# Union type for all content types
MessageContent = Union[TextContent, ImageContent, ToolUseContent, ToolResultContent, str, Dict[str, Any]]


class Message(BaseModel):
    """消息模型"""
    role: Literal["user", "assistant"]
    content: Union[str, List[MessageContent]]


class ToolDefinition(BaseModel):
    """工具定义"""
    name: str
    description: str
    input_schema: Dict[str, Any]


class ToolChoice(BaseModel):
    """工具选择"""
    type: Literal["auto", "any", "tool"] = "auto"
    name: Optional[str] = None


class MessageRequest(BaseModel):
    """消息请求模型 - 兼容 Anthropic API 格式"""
    # Default fallback model; overridden at runtime by the frontend's selected model
    # and configurable via SPRINGO_DEFAULT_CHAT_MODEL in settings
    model: str = Field(default="claude-opus-4-6", description="Model ID")
    messages: List[Message] = Field(..., description="Conversation messages")
    max_tokens: int = Field(default=16384, ge=1, le=200000, description="Max output tokens")
    
    # Optional parameters
    system: Optional[str] = Field(default=None, description="System prompt")
    temperature: Optional[float] = Field(default=None, ge=0, le=1, description="Sampling temperature")
    top_p: Optional[float] = Field(default=None, ge=0, le=1, description="Nucleus sampling")
    top_k: Optional[int] = Field(default=None, ge=0, description="Top-k sampling")
    stop_sequences: Optional[List[str]] = Field(default=None, description="Stop sequences")
    
    # Streaming
    stream: bool = Field(default=False, description="Enable streaming")
    
    # Tools
    tools: Optional[List[ToolDefinition]] = Field(default=None, description="Available tools")
    tool_choice: Optional[ToolChoice] = Field(default=None, description="Tool selection mode")

    # Adaptive thinking (Opus 4.7)
    thinking_enabled: Optional[bool] = Field(default=None, description="Enable adaptive thinking (Opus 4.7)")
    thinking_effort: Optional[str] = Field(default=None, description="Thinking effort: low | medium | high | xhigh | max")

    # Headers passed through
    x_session_id: Optional[str] = Field(default=None, description="Session ID from header")


class MessageAutoRequest(MessageRequest):
    """自动工具执行请求模型"""
    max_tool_iterations: int = Field(default=1000, ge=1, le=2000, description="Max tool loop iterations (safety cap)")
    compact_model: Optional[str] = Field(default=None, description="Model for tool compaction")
    parallel_tool_execution: bool = Field(default=True, description="Enable parallel tool execution")
    working_directory: Optional[str] = Field(default=None, description="Override working directory for tool execution")

    # Design mode — invokes the artifacts-design skill; design_context carries the
    # current artifact's files + pinned element (built by the frontend).
    design_mode: bool = Field(default=False, description="Enable design mode — loads artifacts-design skill guidelines")
    design_context: Optional[str] = Field(default=None, description="Current artifact context (files + pinned element) for iteration")


class ToolExecuteRequest(BaseModel):
    """工具执行请求"""
    name: str = Field(..., description="Tool name")
    input: Dict[str, Any] = Field(default_factory=dict, description="Tool input parameters")


class SessionCreateRequest(BaseModel):
    """会话创建请求"""
    name: Optional[str] = Field(default=None, description="Session name")
    working_directory: Optional[str] = Field(default=None, description="Working directory")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Session metadata")


class SessionUpdateRequest(BaseModel):
    """会话更新请求"""
    messages: List[Dict[str, Any]] = Field(..., description="Messages to save")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Updated metadata")


class PlanGenerateRequest(BaseModel):
    """计划生成请求"""
    task_description: str = Field(..., description="Task to plan")
    session_id: Optional[str] = Field(default=None, description="Session ID for context")
    model: str = Field(default="claude-sonnet-4-6", description="Model to use")
    max_tokens: int = Field(default=8192, description="Max tokens for plan generation")


class PlanFeedbackRequest(BaseModel):
    """Section 反馈请求"""
    section_id: str = Field(..., description="Section ID")
    action: Literal["approve", "reject", "comment"] = Field(..., description="Feedback action")
    feedback: Optional[str] = Field(default=None, description="User feedback text")


class PlanExecuteRequest(BaseModel):
    """计划执行请求"""
    session_id: str = Field(..., description="Session ID")
