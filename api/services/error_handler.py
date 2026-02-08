"""
Claude API 错误处理模块 (FastAPI 版)
支持 AWS Bedrock 和 Anthropic API 的错误类型
"""

import re
import logging
from typing import Dict, Tuple, Optional
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class ErrorCategory(Enum):
    """错误类别"""
    RATE_LIMIT = "rate_limit"
    AUTH = "authentication"
    PERMISSION = "permission"
    VALIDATION = "validation"
    CONTENT = "content"
    SERVICE = "service"
    TIMEOUT = "timeout"
    NETWORK = "network"
    UNKNOWN = "unknown"


@dataclass
class ClaudeError:
    """Claude 错误信息"""
    code: str
    category: ErrorCategory
    message_zh: str
    message_en: str
    suggestion: str
    retry_after: Optional[int]
    http_status: int


# AWS Bedrock 错误映射
BEDROCK_ERRORS: Dict[str, ClaudeError] = {
    "ThrottlingException": ClaudeError(
        code="throttling",
        category=ErrorCategory.RATE_LIMIT,
        message_zh="请求频率限制：AWS Bedrock API 暂时限流",
        message_en="Rate limit exceeded: AWS Bedrock API is temporarily throttled",
        suggestion="请稍等 1-2 分钟后重试，或减少请求频率",
        retry_after=60,
        http_status=429
    ),
    "TooManyTokensException": ClaudeError(
        code="too_many_tokens",
        category=ErrorCategory.RATE_LIMIT,
        message_zh="Token 数量超限：单次请求 token 数过多",
        message_en="Too many tokens in request",
        suggestion="请减少输入内容长度，或分批发送",
        retry_after=30,
        http_status=429
    ),
    "ValidationException": ClaudeError(
        code="validation_error",
        category=ErrorCategory.VALIDATION,
        message_zh="请求格式错误：消息格式或参数无效",
        message_en="Validation error: Invalid message format or parameters",
        suggestion="请检查消息格式是否正确",
        retry_after=None,
        http_status=400
    ),
    "AccessDeniedException": ClaudeError(
        code="access_denied",
        category=ErrorCategory.AUTH,
        message_zh="访问被拒绝：AWS 凭证无效或无权限",
        message_en="Access denied: Invalid AWS credentials or insufficient permissions",
        suggestion="请检查 AWS 凭证配置和模型访问权限",
        retry_after=None,
        http_status=403
    ),
    "ServiceUnavailableException": ClaudeError(
        code="service_unavailable",
        category=ErrorCategory.SERVICE,
        message_zh="服务暂时不可用：AWS Bedrock 服务繁忙",
        message_en="Service unavailable: AWS Bedrock is temporarily busy",
        suggestion="请稍后重试，服务正在恢复中",
        retry_after=30,
        http_status=503
    ),
    "ModelTimeoutException": ClaudeError(
        code="model_timeout",
        category=ErrorCategory.TIMEOUT,
        message_zh="模型响应超时：请求处理时间过长",
        message_en="Model timeout: Request took too long to process",
        suggestion="请简化请求内容或稍后重试",
        retry_after=10,
        http_status=408
    ),
    "ModelStreamErrorException": ClaudeError(
        code="stream_error",
        category=ErrorCategory.SERVICE,
        message_zh="流式响应中断：数据传输异常",
        message_en="Stream error: Data transmission interrupted",
        suggestion="请重新发送请求",
        retry_after=5,
        http_status=500
    ),
    "ResourceNotFoundException": ClaudeError(
        code="resource_not_found",
        category=ErrorCategory.VALIDATION,
        message_zh="模型不存在：指定的模型在当前区域不可用",
        message_en="Resource not found: Model not available in current region",
        suggestion="请检查模型 ID 和 AWS 区域设置",
        retry_after=None,
        http_status=404
    ),
    "ModelNotReadyException": ClaudeError(
        code="model_not_ready",
        category=ErrorCategory.SERVICE,
        message_zh="模型正在预热：服务启动中",
        message_en="Model not ready: Service is warming up",
        suggestion="请等待 30 秒后重试",
        retry_after=30,
        http_status=503
    ),
    "InternalServerException": ClaudeError(
        code="internal_error",
        category=ErrorCategory.SERVICE,
        message_zh="服务内部错误：AWS Bedrock 内部异常",
        message_en="Internal server error: AWS Bedrock internal exception",
        suggestion="请稍后重试，如持续出现请联系支持",
        retry_after=60,
        http_status=500
    ),
    "ModelErrorException": ClaudeError(
        code="model_error",
        category=ErrorCategory.SERVICE,
        message_zh="模型错误：Claude 模型处理异常",
        message_en="Model error: Claude model processing exception",
        suggestion="请简化请求内容或稍后重试",
        retry_after=10,
        http_status=500
    ),
}

# Anthropic API 错误映射
ANTHROPIC_ERRORS: Dict[str, ClaudeError] = {
    "invalid_request_error": ClaudeError(
        code="invalid_request", category=ErrorCategory.VALIDATION,
        message_zh="无效请求：请求参数格式错误",
        message_en="Invalid request: Request parameter format error",
        suggestion="请检查请求参数是否符合 API 规范",
        retry_after=None, http_status=400
    ),
    "authentication_error": ClaudeError(
        code="auth_error", category=ErrorCategory.AUTH,
        message_zh="认证失败：API Key 无效或已过期",
        message_en="Authentication error: Invalid or expired API key",
        suggestion="请检查 API Key 是否正确",
        retry_after=None, http_status=401
    ),
    "permission_error": ClaudeError(
        code="permission_error", category=ErrorCategory.PERMISSION,
        message_zh="权限不足：无权访问此资源",
        message_en="Permission error: No access to this resource",
        suggestion="请检查账户权限设置",
        retry_after=None, http_status=403
    ),
    "not_found_error": ClaudeError(
        code="not_found", category=ErrorCategory.VALIDATION,
        message_zh="资源不存在：请求的资源未找到",
        message_en="Not found: Requested resource not found",
        suggestion="请检查请求路径和资源 ID",
        retry_after=None, http_status=404
    ),
    "rate_limit_error": ClaudeError(
        code="rate_limit", category=ErrorCategory.RATE_LIMIT,
        message_zh="速率限制：请求过于频繁",
        message_en="Rate limit error: Too many requests",
        suggestion="请降低请求频率，稍后重试",
        retry_after=60, http_status=429
    ),
    "api_error": ClaudeError(
        code="api_error", category=ErrorCategory.SERVICE,
        message_zh="API 错误：服务器内部错误",
        message_en="API error: Internal server error",
        suggestion="请稍后重试",
        retry_after=30, http_status=500
    ),
    "overloaded_error": ClaudeError(
        code="overloaded", category=ErrorCategory.SERVICE,
        message_zh="服务过载：Claude API 当前负载过高",
        message_en="Overloaded: Claude API is currently overloaded",
        suggestion="请等待 1-2 分钟后重试",
        retry_after=120, http_status=529
    ),
}

# 内容相关错误
CONTENT_ERRORS: Dict[str, ClaudeError] = {
    "context_length_exceeded": ClaudeError(
        code="context_length_exceeded", category=ErrorCategory.CONTENT,
        message_zh="上下文超限：对话内容超过 200K token 限制",
        message_en="Context length exceeded: Conversation exceeds 200K token limit",
        suggestion="请清理对话历史或开始新对话",
        retry_after=None, http_status=400
    ),
    "output_length_exceeded": ClaudeError(
        code="output_length_exceeded", category=ErrorCategory.CONTENT,
        message_zh="输出超限：响应内容超过 max_tokens 限制",
        message_en="Output length exceeded: Response exceeds max_tokens limit",
        suggestion="请增加 max_tokens 参数值",
        retry_after=None, http_status=400
    ),
    "content_filtered": ClaudeError(
        code="content_filtered", category=ErrorCategory.CONTENT,
        message_zh="内容被过滤：请求内容触发安全过滤",
        message_en="Content filtered: Request triggered safety filter",
        suggestion="请修改请求内容，避免敏感词汇",
        retry_after=None, http_status=400
    ),
    "invalid_tool_use": ClaudeError(
        code="invalid_tool_use", category=ErrorCategory.VALIDATION,
        message_zh="工具调用错误：工具格式或参数无效",
        message_en="Invalid tool use: Tool format or parameters invalid",
        suggestion="请检查工具定义和调用参数",
        retry_after=None, http_status=400
    ),
}

# 网络相关错误
NETWORK_ERRORS: Dict[str, ClaudeError] = {
    "ConnectionError": ClaudeError(
        code="connection_error", category=ErrorCategory.NETWORK,
        message_zh="连接错误：无法连接到服务器",
        message_en="Connection error: Unable to connect to server",
        suggestion="请检查网络连接",
        retry_after=10, http_status=503
    ),
    "TimeoutError": ClaudeError(
        code="timeout", category=ErrorCategory.TIMEOUT,
        message_zh="请求超时：服务器响应超时",
        message_en="Timeout: Server response timeout",
        suggestion="请稍后重试",
        retry_after=10, http_status=408
    ),
    "SSLError": ClaudeError(
        code="ssl_error", category=ErrorCategory.NETWORK,
        message_zh="SSL 错误：安全连接失败",
        message_en="SSL error: Secure connection failed",
        suggestion="请检查网络环境和证书配置",
        retry_after=None, http_status=495
    ),
}

# 客户端操作错误
CLIENT_ERRORS: Dict[str, ClaudeError] = {
    "Access denied": ClaudeError(
        code="access_denied_path", category=ErrorCategory.PERMISSION,
        message_zh="访问被拒绝：路径超出允许的目录范围",
        message_en="Access denied: Path is outside allowed directories",
        suggestion="请确保操作在工作目录内进行",
        retry_after=None, http_status=403
    ),
    "File not found": ClaudeError(
        code="file_not_found", category=ErrorCategory.VALIDATION,
        message_zh="文件不存在：指定的文件未找到",
        message_en="File not found: The specified file does not exist",
        suggestion="请检查文件路径是否正确",
        retry_after=None, http_status=404
    ),
    "Command blocked": ClaudeError(
        code="command_blocked", category=ErrorCategory.PERMISSION,
        message_zh="命令被阻止：该命令因安全原因被禁止执行",
        message_en="Command blocked: This command is blocked for safety reasons",
        suggestion="请避免使用危险命令如 rm -rf /",
        retry_after=None, http_status=403
    ),
    "Command timed out": ClaudeError(
        code="command_timeout", category=ErrorCategory.TIMEOUT,
        message_zh="命令超时：命令执行时间过长",
        message_en="Command timed out: Command execution took too long",
        suggestion="请简化命令或增加超时时间",
        retry_after=5, http_status=408
    ),
    "Unknown tool": ClaudeError(
        code="unknown_tool", category=ErrorCategory.VALIDATION,
        message_zh="未知工具：指定的工具不存在",
        message_en="Unknown tool: The specified tool does not exist",
        suggestion="请检查工具名称是否正确",
        retry_after=None, http_status=404
    ),
    "Directory not found": ClaudeError(
        code="directory_not_found", category=ErrorCategory.VALIDATION,
        message_zh="目录不存在：指定的目录未找到",
        message_en="Directory not found: The specified directory does not exist",
        suggestion="请检查目录路径是否正确",
        retry_after=None, http_status=404
    ),
    "Not a file": ClaudeError(
        code="not_a_file", category=ErrorCategory.VALIDATION,
        message_zh="路径错误：指定路径不是文件",
        message_en="Not a file: The specified path is not a file",
        suggestion="请确认路径指向文件而非目录",
        retry_after=None, http_status=400
    ),
    "Not a directory": ClaudeError(
        code="not_a_directory", category=ErrorCategory.VALIDATION,
        message_zh="路径错误：指定路径不是目录",
        message_en="Not a directory: The specified path is not a directory",
        suggestion="请确认路径指向目录而非文件",
        retry_after=None, http_status=400
    ),
    "File too large": ClaudeError(
        code="file_too_large", category=ErrorCategory.VALIDATION,
        message_zh="文件过大：文件超过 1MB 大小限制",
        message_en="File too large: File exceeds 1MB size limit",
        suggestion="请分块读取文件或压缩后再操作",
        retry_after=None, http_status=413
    ),
    "Directory is not empty": ClaudeError(
        code="directory_not_empty", category=ErrorCategory.VALIDATION,
        message_zh="目录非空：无法删除非空目录",
        message_en="Directory is not empty: Cannot delete non-empty directory",
        suggestion="请使用 rm -r 命令删除非空目录",
        retry_after=None, http_status=400
    ),
    "Working directory not found": ClaudeError(
        code="working_dir_not_found", category=ErrorCategory.VALIDATION,
        message_zh="工作目录不存在：指定的工作目录未找到",
        message_en="Working directory not found: The specified working directory does not exist",
        suggestion="请设置正确的工作目录",
        retry_after=None, http_status=404
    ),
    "Not a git repository": ClaudeError(
        code="not_git_repo", category=ErrorCategory.VALIDATION,
        message_zh="非 Git 仓库：当前目录不是 Git 仓库",
        message_en="Not a git repository: Current directory is not a git repository",
        suggestion="请在 Git 仓库目录中执行此操作",
        retry_after=None, http_status=400
    ),
    "Git command timed out": ClaudeError(
        code="git_timeout", category=ErrorCategory.TIMEOUT,
        message_zh="Git 命令超时：Git 操作时间过长",
        message_en="Git command timed out: Git operation took too long",
        suggestion="请检查网络连接或仓库大小",
        retry_after=10, http_status=408
    ),
    "No files specified": ClaudeError(
        code="no_files_specified", category=ErrorCategory.VALIDATION,
        message_zh="未指定文件：请提供要操作的文件列表",
        message_en="No files specified: Please provide files to operate on",
        suggestion="请指定要添加/操作的文件",
        retry_after=None, http_status=400
    ),
    "Commit message is required": ClaudeError(
        code="commit_message_required", category=ErrorCategory.VALIDATION,
        message_zh="缺少提交信息：Git commit 需要提交信息",
        message_en="Commit message is required: Git commit requires a message",
        suggestion="请提供 commit message",
        retry_after=None, http_status=400
    ),
    "Branch name is required": ClaudeError(
        code="branch_name_required", category=ErrorCategory.VALIDATION,
        message_zh="缺少分支名：请提供分支名称",
        message_en="Branch name is required: Please provide a branch name",
        suggestion="请指定分支名称",
        retry_after=None, http_status=400
    ),
    "Tool call incomplete": ClaudeError(
        code="tool_call_incomplete", category=ErrorCategory.VALIDATION,
        message_zh="工具调用不完整：缺少必需的参数",
        message_en="Tool call incomplete: Required parameters missing",
        suggestion="模型响应可能被截断，请重试",
        retry_after=5, http_status=400
    ),
    "Unknown action": ClaudeError(
        code="unknown_action", category=ErrorCategory.VALIDATION,
        message_zh="未知操作：指定的 action 不存在",
        message_en="Unknown action: The specified action does not exist",
        suggestion="请检查 action 参数是否正确",
        retry_after=None, http_status=400
    ),
    "Unknown task": ClaudeError(
        code="unknown_task", category=ErrorCategory.VALIDATION,
        message_zh="未知任务：指定的任务 ID 不存在",
        message_en="Unknown task: The specified task ID does not exist",
        suggestion="请检查任务 ID 是否正确",
        retry_after=None, http_status=404
    ),
    "Invalid directory": ClaudeError(
        code="invalid_directory", category=ErrorCategory.VALIDATION,
        message_zh="无效目录：指定的目录不存在或无效",
        message_en="Invalid directory: The specified directory does not exist or is invalid",
        suggestion="请设置一个存在的有效目录",
        retry_after=None, http_status=400
    ),
    "No messages provided": ClaudeError(
        code="no_messages", category=ErrorCategory.VALIDATION,
        message_zh="缺少消息：请求中未包含消息内容",
        message_en="No messages provided: Request does not contain any messages",
        suggestion="请确保请求包含消息内容",
        retry_after=None, http_status=400
    ),
    "Skill .* not found": ClaudeError(
        code="skill_not_found", category=ErrorCategory.VALIDATION,
        message_zh="技能不存在：指定的技能未找到",
        message_en="Skill not found: The specified skill does not exist",
        suggestion="请检查技能名称是否正确",
        retry_after=None, http_status=404
    ),
}

# 合并所有错误映射
ALL_ERRORS = {**BEDROCK_ERRORS, **ANTHROPIC_ERRORS, **CONTENT_ERRORS, **NETWORK_ERRORS, **CLIENT_ERRORS}


def parse_error(error: Exception) -> ClaudeError:
    """解析错误并返回结构化的错误信息"""
    error_str = str(error)
    error_type = type(error).__name__

    # 1. 检查错误类型名称
    if error_type in ALL_ERRORS:
        return ALL_ERRORS[error_type]

    # 2. 检查错误字符串中是否包含已知错误类型
    for error_key, error_info in ALL_ERRORS.items():
        if error_key in error_str:
            return error_info

    # 3. 正则匹配常见错误模式
    patterns = [
        (r"Too many tokens", "TooManyTokensException"),
        (r"rate.?limit", "rate_limit_error"),
        (r"throttl", "ThrottlingException"),
        (r"access.?denied", "AccessDeniedException"),
        (r"unauthorized", "authentication_error"),
        (r"forbidden", "permission_error"),
        (r"not.?found", "not_found_error"),
        (r"timeout", "TimeoutError"),
        (r"overload", "overloaded_error"),
        (r"context.?length", "context_length_exceeded"),
        (r"max.?tokens", "output_length_exceeded"),
        (r"content.?filter", "content_filtered"),
        (r"connection", "ConnectionError"),
        (r"ssl", "SSLError"),
    ]

    error_lower = error_str.lower()
    for pattern, error_key in patterns:
        if re.search(pattern, error_lower, re.IGNORECASE):
            if error_key in ALL_ERRORS:
                return ALL_ERRORS[error_key]

    # 4. 返回未知错误
    return ClaudeError(
        code="unknown_error",
        category=ErrorCategory.UNKNOWN,
        message_zh=f"未知错误：{error_str[:200]}",
        message_en=f"Unknown error: {error_str[:200]}",
        suggestion="请稍后重试，如持续出现请联系支持",
        retry_after=30,
        http_status=500
    )


def format_error_response(error: Exception, lang: str = "zh") -> Dict:
    """格式化错误响应"""
    parsed = parse_error(error)
    message = parsed.message_zh if lang == "zh" else parsed.message_en

    response = {
        "type": "error",
        "error": {
            "type": parsed.category.value,
            "code": parsed.code,
            "message": message,
            "suggestion": parsed.suggestion,
        }
    }

    if parsed.retry_after:
        response["error"]["retry_after"] = parsed.retry_after

    return response


def get_user_friendly_message(error: Exception, lang: str = "zh") -> str:
    """获取用户友好的错误信息"""
    parsed = parse_error(error)
    message = parsed.message_zh if lang == "zh" else parsed.message_en
    return f"{message}。{parsed.suggestion}"


def should_retry(error: Exception) -> Tuple[bool, int]:
    """判断是否应该重试"""
    parsed = parse_error(error)
    retryable_categories = {
        ErrorCategory.RATE_LIMIT,
        ErrorCategory.SERVICE,
        ErrorCategory.TIMEOUT,
        ErrorCategory.NETWORK,
    }

    if parsed.category in retryable_categories and parsed.retry_after:
        return True, parsed.retry_after

    return False, 0


def get_http_status(error: Exception) -> int:
    """获取对应的 HTTP 状态码"""
    parsed = parse_error(error)
    return parsed.http_status


__all__ = [
    'parse_error', 'format_error_response', 'get_user_friendly_message',
    'should_retry', 'get_http_status', 'ClaudeError', 'ErrorCategory', 'ALL_ERRORS',
]
