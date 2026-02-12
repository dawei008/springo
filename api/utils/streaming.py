"""
Springo SSE Streaming Utilities
SSE 流处理工具
"""
import json
import asyncio
import logging
from typing import AsyncGenerator, Any, Dict, Optional
from datetime import datetime

from fastapi import Request
from fastapi.responses import StreamingResponse

logger = logging.getLogger(__name__)


async def sse_generator(
    async_gen: AsyncGenerator[str, None],
    request: Optional[Request] = None
) -> AsyncGenerator[str, None]:
    """
    包装异步生成器，处理客户端断开连接
    
    Args:
        async_gen: 原始异步生成器
        request: FastAPI request (用于检测断开连接)
    
    Yields:
        SSE formatted strings
    """
    try:
        async for event in async_gen:
            # Check if client disconnected
            if request and await request.is_disconnected():
                logger.warning("SSE client disconnected - stopping generator")
                break
            yield event
            
    except asyncio.CancelledError:
        logger.warning("SSE generator cancelled")
        raise
    except GeneratorExit:
        logger.warning("SSE generator exit")
    except Exception as e:
        logger.error(f"SSE generator error: {e}")
        # Try to send error event
        try:
            error_data = {
                'type': 'error',
                'error': {'type': 'stream_error', 'message': str(e)}
            }
            yield f"event: error\ndata: {json.dumps(error_data)}\n\n"
        except:
            pass
    finally:
        logger.debug("SSE generator finished")


def create_sse_response(
    generator: AsyncGenerator[str, None],
    request: Optional[Request] = None
) -> StreamingResponse:
    """
    创建 SSE StreamingResponse
    
    Args:
        generator: SSE 事件生成器
        request: FastAPI request
    
    Returns:
        StreamingResponse with SSE headers
    """
    return StreamingResponse(
        sse_generator(generator, request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "Transfer-Encoding": "chunked"
        }
    )


def format_sse_event(event_type: str, data: Any) -> str:
    """
    格式化 SSE 事件
    
    Args:
        event_type: 事件类型
        data: 事件数据 (will be JSON serialized)
    
    Returns:
        SSE formatted string
    """
    if isinstance(data, str):
        json_data = data
    else:
        json_data = json.dumps(data)
    
    return f"event: {event_type}\ndata: {json_data}\n\n"


def format_sse_data(data: Any) -> str:
    """
    格式化 SSE 数据行 (无事件类型)
    
    Args:
        data: 事件数据
    
    Returns:
        SSE formatted string
    """
    if isinstance(data, str):
        return f"data: {data}\n\n"
    return f"data: {json.dumps(data)}\n\n"


async def heartbeat_generator(
    interval: float = 10.0,
    tool_id: Optional[str] = None
) -> AsyncGenerator[str, None]:
    """
    心跳事件生成器
    
    Args:
        interval: 心跳间隔 (秒)
        tool_id: 关联的工具 ID
    
    Yields:
        SSE heartbeat events
    """
    start_time = asyncio.get_event_loop().time()
    
    while True:
        await asyncio.sleep(interval)
        elapsed = asyncio.get_event_loop().time() - start_time
        
        heartbeat_data = {
            'type': 'heartbeat',
            'elapsed': round(elapsed, 2),
            'timestamp': datetime.now().isoformat()
        }
        if tool_id:
            heartbeat_data['tool_use_id'] = tool_id
        
        yield format_sse_event('heartbeat', heartbeat_data)


class SSEEventBuilder:
    """SSE 事件构建器"""
    
    @staticmethod
    def message_start(message: Dict[str, Any]) -> str:
        """构建 message_start 事件"""
        return format_sse_event('message_start', {
            'type': 'message_start',
            'message': message
        })
    
    @staticmethod
    def content_block_start(index: int, content_block: Dict[str, Any]) -> str:
        """构建 content_block_start 事件"""
        return format_sse_event('content_block_start', {
            'type': 'content_block_start',
            'index': index,
            'content_block': content_block
        })
    
    @staticmethod
    def content_block_delta(index: int, delta: Dict[str, Any]) -> str:
        """构建 content_block_delta 事件"""
        return format_sse_event('content_block_delta', {
            'type': 'content_block_delta',
            'index': index,
            'delta': delta
        })
    
    @staticmethod
    def content_block_stop(index: int) -> str:
        """构建 content_block_stop 事件"""
        return format_sse_event('content_block_stop', {
            'type': 'content_block_stop',
            'index': index
        })
    
    @staticmethod
    def message_delta(delta: Dict[str, Any], usage: Dict[str, int]) -> str:
        """构建 message_delta 事件"""
        return format_sse_event('message_delta', {
            'type': 'message_delta',
            'delta': delta,
            'usage': usage
        })
    
    @staticmethod
    def message_stop() -> str:
        """构建 message_stop 事件"""
        return format_sse_event('message_stop', {'type': 'message_stop'})
    
    @staticmethod
    def error(message: str, error_type: str = "api_error") -> str:
        """构建 error 事件"""
        return format_sse_event('error', {
            'type': 'error',
            'error': {
                'type': error_type,
                'message': message
            }
        })
    
    @staticmethod
    def tool_start(tool_id: str, tool_name: str) -> str:
        """构建 tool_start 事件"""
        return format_sse_event('tool_start', {
            'type': 'tool_start',
            'tool_use_id': tool_id,
            'tool_name': tool_name
        })
    
    @staticmethod
    def tool_result(
        tool_id: str,
        tool_name: str,
        result: Any,
        is_error: bool = False,
        elapsed: float = 0
    ) -> str:
        """构建 tool_result 事件"""
        return format_sse_event('tool_result', {
            'type': 'tool_result',
            'tool_use_id': tool_id,
            'tool_name': tool_name,
            'result': result,
            'is_error': is_error,
            'elapsed': round(elapsed, 2)
        })
    
    @staticmethod
    def heartbeat(elapsed: float, tool_id: Optional[str] = None) -> str:
        """构建 heartbeat 事件"""
        data = {
            'type': 'heartbeat',
            'elapsed': round(elapsed, 2)
        }
        if tool_id:
            data['tool_use_id'] = tool_id
        return format_sse_event('heartbeat', data)
    
    @staticmethod
    def context_compact(reason: str, model: str, tokens_before: int) -> str:
        """构建 context_compact 事件（开始压缩）"""
        return format_sse_event('context_compact', {
            'type': 'context_compact',
            'reason': reason,
            'model': model,
            'tokens_before': tokens_before
        })

    @staticmethod
    def context_compact_done(
        messages_before: int, messages_after: int, tokens_after: int
    ) -> str:
        """构建 context_compact_done 事件（压缩完成）"""
        return format_sse_event('context_compact_done', {
            'type': 'context_compact_done',
            'messages_before': messages_before,
            'messages_after': messages_after,
            'tokens_after': tokens_after
        })

    @staticmethod
    def context_compact_failed(error: str) -> str:
        """构建 context_compact_failed 事件"""
        return format_sse_event('context_compact_failed', {
            'type': 'context_compact_failed',
            'error': error
        })

    @staticmethod
    def messages_updated(session_id: str, messages: list, token_count: int) -> str:
        """构建 messages_updated 事件（通知前端消息已更新）"""
        return format_sse_event('messages_updated', {
            'type': 'messages_updated',
            'session_id': session_id,
            'messages': messages,
            'token_count': token_count
        })

    @staticmethod
    def skill_injected(skill_name: str) -> str:
        """构建 skill_injected 事件"""
        return format_sse_event('skill_injected', {
            'type': 'skill_injected',
            'skill_name': skill_name
        })

    @staticmethod
    def tool_execution_start(tools: list) -> str:
        """构建 tool_execution_start 批量事件（一组工具即将开始执行）"""
        return format_sse_event('tool_execution_start', {
            'type': 'tool_execution_start',
            'tools': [{"id": t.get("id", ""), "name": t.get("name", ""), "input": t.get("input", {})} for t in tools],
            'count': len(tools),
            'timestamp': datetime.now().isoformat(),
        })

    @staticmethod
    def tool_execution_complete(count: int, total_elapsed: float) -> str:
        """构建 tool_execution_complete 批量事件（一组工具全部执行完成）"""
        return format_sse_event('tool_execution_complete', {
            'type': 'tool_execution_complete',
            'count': count,
            'total_elapsed': round(total_elapsed, 2),
            'timestamp': datetime.now().isoformat(),
        })

    # === Agent Team SSE Events ===

    @staticmethod
    def team_spawned(team_id: str, agents: list, user_request: str) -> str:
        """Team created with agents"""
        return format_sse_event('team_spawned', {
            'type': 'team_spawned',
            'team_id': team_id,
            'agents': agents,
            'user_request': user_request,
            'timestamp': datetime.now().isoformat(),
        })

    @staticmethod
    def team_planning(team_id: str) -> str:
        """Orchestrator is decomposing the task"""
        return format_sse_event('team_planning', {
            'type': 'team_planning',
            'team_id': team_id,
            'timestamp': datetime.now().isoformat(),
        })

    @staticmethod
    def team_task_board(team_id: str, tasks: list) -> str:
        """Task board updated with decomposed tasks"""
        return format_sse_event('team_task_board', {
            'type': 'team_task_board',
            'team_id': team_id,
            'tasks': tasks,
            'timestamp': datetime.now().isoformat(),
        })

    @staticmethod
    def team_agent_start(team_id: str, agent_id: str, role: str, task_title: str) -> str:
        """An agent started working on a task"""
        return format_sse_event('team_agent_start', {
            'type': 'team_agent_start',
            'team_id': team_id,
            'agent_id': agent_id,
            'role': role,
            'task_title': task_title,
            'timestamp': datetime.now().isoformat(),
        })

    @staticmethod
    def team_agent_progress(team_id: str, agent_id: str, role: str, status: str, preview: str = "") -> str:
        """Agent progress update (thinking/executing)"""
        return format_sse_event('team_agent_progress', {
            'type': 'team_agent_progress',
            'team_id': team_id,
            'agent_id': agent_id,
            'role': role,
            'status': status,
            'preview': preview[:200] if preview else "",
            'timestamp': datetime.now().isoformat(),
        })

    @staticmethod
    def team_agent_complete(team_id: str, agent_id: str, role: str, task_title: str, findings: str, tokens: dict) -> str:
        """Agent completed its task"""
        return format_sse_event('team_agent_complete', {
            'type': 'team_agent_complete',
            'team_id': team_id,
            'agent_id': agent_id,
            'role': role,
            'task_title': task_title,
            'findings': findings,
            'tokens': tokens,
            'timestamp': datetime.now().isoformat(),
        })

    @staticmethod
    def team_agent_error(team_id: str, agent_id: str, role: str, error: str) -> str:
        """Agent encountered an error"""
        return format_sse_event('team_agent_error', {
            'type': 'team_agent_error',
            'team_id': team_id,
            'agent_id': agent_id,
            'role': role,
            'error': error,
            'timestamp': datetime.now().isoformat(),
        })

    @staticmethod
    def team_agent_delta(team_id: str, agent_id: str, role: str, delta: str) -> str:
        """Streaming text chunk from an agent"""
        return format_sse_event('team_agent_delta', {
            'type': 'team_agent_delta',
            'team_id': team_id,
            'agent_id': agent_id,
            'role': role,
            'delta': delta,
        })

    @staticmethod
    def team_agent_tool(team_id: str, agent_id: str, role: str,
                        tool_name: str, status: str, result_preview: str = "") -> str:
        """Agent tool execution event (start / complete / error)"""
        return format_sse_event('team_agent_tool', {
            'type': 'team_agent_tool',
            'team_id': team_id,
            'agent_id': agent_id,
            'role': role,
            'tool_name': tool_name,
            'status': status,
            'result_preview': result_preview[:200] if result_preview else "",
        })

    @staticmethod
    def team_synthesis_delta(team_id: str, delta: str) -> str:
        """Streaming text chunk from synthesis phase"""
        return format_sse_event('team_synthesis_delta', {
            'type': 'team_synthesis_delta',
            'team_id': team_id,
            'delta': delta,
        })

    @staticmethod
    def team_synthesizing(team_id: str) -> str:
        """Orchestrator is synthesizing results"""
        return format_sse_event('team_synthesizing', {
            'type': 'team_synthesizing',
            'team_id': team_id,
            'timestamp': datetime.now().isoformat(),
        })

    @staticmethod
    def team_complete(team_id: str, result: str, total_tokens: dict) -> str:
        """Team execution complete with final result"""
        return format_sse_event('team_complete', {
            'type': 'team_complete',
            'team_id': team_id,
            'result': result,
            'total_tokens': total_tokens,
            'timestamp': datetime.now().isoformat(),
        })

    @staticmethod
    def team_error(team_id: str, error: str) -> str:
        """Team-level error"""
        return format_sse_event('team_error', {
            'type': 'team_error',
            'team_id': team_id,
            'error': error,
            'timestamp': datetime.now().isoformat(),
        })

    # === Collaborative Team SSE Events ===

    @staticmethod
    def team_agent_message(
        team_id: str, sender: str, recipient: str,
        content: str, summary: str = "", message_id: str = "",
    ) -> str:
        """Direct message sent between agents"""
        return format_sse_event('team_agent_message', {
            'type': 'team_agent_message',
            'team_id': team_id,
            'sender': sender,
            'recipient': recipient,
            'content': content,
            'summary': summary,
            'message_id': message_id,
            'timestamp': datetime.now().isoformat(),
        })

    @staticmethod
    def team_agent_broadcast(
        team_id: str, sender: str,
        content: str, summary: str = "", message_id: str = "",
    ) -> str:
        """Broadcast message sent to all agents"""
        return format_sse_event('team_agent_broadcast', {
            'type': 'team_agent_broadcast',
            'team_id': team_id,
            'sender': sender,
            'content': content,
            'summary': summary,
            'message_id': message_id,
            'timestamp': datetime.now().isoformat(),
        })

    @staticmethod
    def team_agent_idle(team_id: str, agent_name: str) -> str:
        """Agent went idle (waiting for input)"""
        return format_sse_event('team_agent_idle', {
            'type': 'team_agent_idle',
            'team_id': team_id,
            'agent_name': agent_name,
            'timestamp': datetime.now().isoformat(),
        })

    @staticmethod
    def team_agent_shutdown(team_id: str, agent_name: str) -> str:
        """Agent shut down"""
        return format_sse_event('team_agent_shutdown', {
            'type': 'team_agent_shutdown',
            'team_id': team_id,
            'agent_name': agent_name,
            'timestamp': datetime.now().isoformat(),
        })

    @staticmethod
    def team_task_created(
        team_id: str, task_id: str, title: str,
        description: str = "", owner: Optional[str] = None,
    ) -> str:
        """New task created on the shared task board"""
        return format_sse_event('team_task_created', {
            'type': 'team_task_created',
            'team_id': team_id,
            'task_id': task_id,
            'title': title,
            'description': description,
            'owner': owner,
            'timestamp': datetime.now().isoformat(),
        })

    @staticmethod
    def team_task_updated(
        team_id: str, task_id: str, status: str,
        owner: Optional[str] = None, title: str = "",
    ) -> str:
        """Task updated on the shared task board"""
        return format_sse_event('team_task_updated', {
            'type': 'team_task_updated',
            'team_id': team_id,
            'task_id': task_id,
            'status': status,
            'owner': owner,
            'title': title,
            'timestamp': datetime.now().isoformat(),
        })

    @staticmethod
    def team_task_unblocked(
        team_id: str, task_id: str, title: str,
        owner: Optional[str] = None,
    ) -> str:
        """Task became unblocked (all dependencies resolved)"""
        return format_sse_event('team_task_unblocked', {
            'type': 'team_task_unblocked',
            'team_id': team_id,
            'task_id': task_id,
            'title': title,
            'owner': owner,
            'timestamp': datetime.now().isoformat(),
        })

    @staticmethod
    def team_ask_user(
        team_id: str, agent_name: str,
        question: str, options: list,
    ) -> str:
        """Agent is asking the user a question"""
        return format_sse_event('team_ask_user', {
            'type': 'team_ask_user',
            'team_id': team_id,
            'agent_name': agent_name,
            'question': question,
            'options': options,
            'timestamp': datetime.now().isoformat(),
        })

    @staticmethod
    def done() -> str:
        """构建完成标记"""
        return "data: [DONE]\n\n"
