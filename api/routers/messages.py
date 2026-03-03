"""
Springo Messages Router
消息 API 路由 - /v1/messages 和 /v1/messages-auto
"""
import json
import uuid
import logging
import asyncio
from typing import Optional, Dict, Any, List, AsyncGenerator
from datetime import datetime

from fastapi import APIRouter, Request, HTTPException, Header, Depends
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from ..config import settings
from ..models.requests import MessageRequest, MessageAutoRequest
from ..models.responses import MessageResponse, ErrorResponse, Usage
from ..services.bedrock import get_bedrock_service, BedrockService, get_model_limits
from ..services.vendor_router import get_vendor_router, VendorRouter
from ..services.model_registry import MODEL_REGISTRY
from ..services.mcp_manager import get_mcp_manager, MCPManager
from ..services.context_manager import (
    count_messages_tokens, should_summarize, summarize_context,
    prepare_messages_for_api, truncate_tool_results, repair_orphan_tool_uses,
    save_tool_result, save_summary_event,
    split_messages_for_summary, create_summary_messages,
    check_and_prepare_auto_summary, pre_compaction_memory_flush,
    MAX_INLINE_OUTPUT_SIZE,
    RECENT_MESSAGES_TO_KEEP,
)
from ..services.session_store import get_session_store
from ..services.error_handler import format_error_response as eh_format_error, get_http_status
from ..utils.streaming import create_sse_response, SSEEventBuilder
from .skills import consume_active_skill

logger = logging.getLogger(__name__)

router = APIRouter()

# ── Session cancellation registry ──
# Maps session_id → asyncio.Event.  When set(), the streaming loop breaks.
_cancel_events: Dict[str, asyncio.Event] = {}


def _get_cancel_event(session_id: str) -> asyncio.Event:
    """Get or create a cancellation event for a session."""
    if session_id not in _cancel_events:
        _cancel_events[session_id] = asyncio.Event()
    return _cancel_events[session_id]


def _cleanup_cancel_event(session_id: str) -> None:
    _cancel_events.pop(session_id, None)


# Dependency: Get Bedrock service (kept for backward compat)
async def get_bedrock() -> BedrockService:
    return get_bedrock_service()

# Dependency: Get VendorRouter (routes to correct backend)
async def get_router() -> VendorRouter:
    return get_vendor_router()


@router.post("/messages")
async def messages_api(
    request: Request,
    bedrock: VendorRouter = Depends(get_router),
    x_session_id: Optional[str] = Header(default=None)
):
    """
    Claude Messages API - 调用 Bedrock
    
    支持流式和非流式响应。
    """
    try:
        # Parse request body
        body = await request.json()
        try:
            msg_request = MessageRequest(**body)
        except ValidationError as ve:
            raise HTTPException(status_code=422, detail={
                "type": "validation_error",
                "error": {"type": "invalid_request", "message": str(ve)}
            })
        
        # Validate model against registry
        if msg_request.model not in MODEL_REGISTRY:
            valid_models = sorted(MODEL_REGISTRY.keys())
            raise HTTPException(
                status_code=400,
                detail={
                    "type": "error",
                    "error": {
                        "type": "invalid_request",
                        "message": f"Unknown model: {msg_request.model}. Valid models: {valid_models}"
                    }
                }
            )

        logger.info(f"Messages API: model={msg_request.model}, stream={msg_request.stream}, messages={len(msg_request.messages)}")

        # Get working directory from session state
        from ..services.session_state import get_working_dir
        working_dir = get_working_dir() or None
        
        # Get tools if available
        tools = msg_request.tools or []  # TODO: Get from MCP manager
        
        # Convert to Bedrock format
        model_id, bedrock_body = bedrock.convert_request_to_bedrock(
            body,
            include_tools=bool(tools),
            tools=[t.model_dump() if hasattr(t, 'model_dump') else t for t in tools] if tools else None,
            working_dir=working_dir
        )
        
        original_model = msg_request.model
        api_format = bedrock.get_api_format(original_model)

        if msg_request.stream:
            # Streaming response
            async def stream_generator() -> AsyncGenerator[str, None]:
                async for event in bedrock.invoke_model_stream(model_id, bedrock_body, original_model, api_format=api_format):
                    yield event

            return create_sse_response(stream_generator(), request)
        else:
            # Non-streaming response
            bedrock_response = await bedrock.invoke_model(model_id, bedrock_body, api_format=api_format)
            
            response = {
                "id": f"msg_{uuid.uuid4().hex[:24]}",
                "type": "message",
                "role": "assistant",
                "content": bedrock_response.get("content", []),
                "model": original_model,
                "stop_reason": bedrock_response.get("stop_reason"),
                "stop_sequence": bedrock_response.get("stop_sequence"),
                "usage": {
                    "input_tokens": bedrock_response.get("usage", {}).get("input_tokens", 0),
                    "output_tokens": bedrock_response.get("usage", {}).get("output_tokens", 0),
                }
            }
            
            return JSONResponse(
                content=response,
                headers={"x-request-id": str(uuid.uuid4())}
            )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Messages API error: {e}")
        
        error_response = {
            "type": "error",
            "error": {
                "type": "api_error",
                "message": str(e)
            }
        }
        
        raise HTTPException(status_code=500, detail=error_response)


@router.post("/messages-auto")
async def messages_auto_api(
    request: Request,
    bedrock: VendorRouter = Depends(get_router),
    x_session_id: Optional[str] = Header(default=None)
):
    """
    自动工具执行 API - 消除前端往返延迟
    
    服务端自动处理 tool_use -> tool_result 循环，直到：
    1. 模型返回 stop_reason != "tool_use"
    2. 达到 max_tool_iterations
    3. 发生错误
    """
    try:
        body = await request.json()
        try:
            msg_request = MessageAutoRequest(**body)
        except ValidationError as ve:
            raise HTTPException(status_code=422, detail={
                "type": "validation_error",
                "error": {"type": "invalid_request", "message": str(ve)}
            })
        
        # Validate model against registry
        if msg_request.model not in MODEL_REGISTRY:
            valid_models = sorted(MODEL_REGISTRY.keys())
            raise HTTPException(
                status_code=400,
                detail={
                    "type": "error",
                    "error": {
                        "type": "invalid_request",
                        "message": f"Unknown model: {msg_request.model}. Valid models: {valid_models}"
                    }
                }
            )

        logger.info(f"Messages Auto API: model={msg_request.model}, max_iterations={msg_request.max_tool_iterations}")

        # Read session_id from header OR body
        session_id = x_session_id or body.get("session_id")
        compact_model = msg_request.compact_model

        # Validate compact_model if provided
        if compact_model and compact_model not in MODEL_REGISTRY:
            valid_models = sorted(MODEL_REGISTRY.keys())
            raise HTTPException(
                status_code=400,
                detail={
                    "type": "error",
                    "error": {
                        "type": "invalid_request",
                        "message": f"Unknown compact_model: {compact_model}. Valid models: {valid_models}"
                    }
                }
            )

        # Get working directory: request override > session state
        from ..services.session_state import get_working_dir
        working_dir = msg_request.working_directory or get_working_dir() or None

        # Get tools: use request tools if provided, otherwise load from MCPManager
        tools = msg_request.tools or []
        if not tools:
            try:
                mcp_mgr = await get_mcp_manager()
                tool_defs = mcp_mgr.get_tool_definitions()
                if tool_defs:
                    tools = tool_defs
                    logger.info(f"Loaded {len(tools)} tools from MCPManager")
            except Exception as e:
                logger.warning(f"Failed to load tools from MCPManager: {e}")
        
        original_model = msg_request.model
        max_iterations = msg_request.max_tool_iterations

        # Track user turn + session for auto-unload and todo persistence
        if session_id:
            try:
                from api.services.session_state import (
                    set_current_session_id, load_todos, set_todos,
                    increment_user_turn,
                )
                set_current_session_id(session_id)
                saved_todos = load_todos(session_id)
                if saved_todos:
                    set_todos(saved_todos)
                turn = increment_user_turn()
                logger.debug(f"[{session_id}] User turn {turn} (auto-unload tracking)")
            except Exception:
                pass

        if msg_request.stream:
            # Streaming auto-tool execution
            async def auto_stream_generator() -> AsyncGenerator[str, None]:
                # Set up cancellation token for this session
                cancel_event: Optional[asyncio.Event] = None
                if session_id:
                    cancel_event = _get_cancel_event(session_id)
                    # Propagate session_id to mcp_tools so subprocesses can be tracked
                    try:
                        from mcp_tools.session import get_session_state
                        get_session_state()["session_id"] = session_id
                    except Exception:
                        pass
                    # Note: session tracking + todo restore + user turn increment
                    # now handled before the stream/non-stream branch (above)

                messages = [m.model_dump() if hasattr(m, 'model_dump') else m for m in msg_request.messages]
                iteration = 0
                system_extra = ""

                _saved_msg_count = 0  # tracks how many messages have been persisted

                def _auto_save_session(msgs, extra_meta=None):
                    """Auto-save session to JSONL after each iteration.

                    Uses incremental append for subsequent saves to avoid
                    rewriting the entire file + re-queuing all messages on
                    every tool call.
                    """
                    nonlocal _saved_msg_count
                    if not session_id:
                        return
                    try:
                        import re
                        store = get_session_store()

                        # Build metadata (title + tokens)
                        existing_meta = store.get_session_metadata(session_id)
                        has_custom_title = existing_meta.get("isCustomTitle", False) if existing_meta else False

                        meta: dict = {}
                        if has_custom_title:
                            meta["title"] = existing_meta.get("title", "New Chat")
                            meta["isCustomTitle"] = True
                        else:
                            title = ""
                            for m in reversed(msgs):
                                if m.get("role") == "user":
                                    content = m.get("content", "")
                                    if isinstance(content, str) and content:
                                        clean = re.sub(r'^\[Current time:[^\]]*\]\s*', '', content)
                                        skill_match = re.match(r'^<skill\s+name="([^"]+)">[\s\S]*?</skill>\s*', clean)
                                        if skill_match:
                                            after_skill = clean[skill_match.end():]
                                            user_req = re.sub(r'^User request:\s*', '', after_skill, flags=re.IGNORECASE)
                                            user_req = re.sub(r'\s*Please follow the skill instructions above.*$', '', user_req, flags=re.DOTALL).strip()
                                            clean = f"/{skill_match.group(1)} {user_req}" if user_req else f"/{skill_match.group(1)}"
                                        if clean:
                                            title = clean[:30] + ("..." if len(clean) > 30 else "")
                                        break
                                    elif isinstance(content, list):
                                        continue
                            meta["title"] = title or "New Chat"

                        meta["tokens"] = count_messages_tokens(msgs)
                        if extra_meta:
                            meta.update(extra_meta)

                        if _saved_msg_count == 0:
                            # First save: full write with metadata + all messages
                            store.save_session_complete(session_id, msgs, metadata=meta)
                            _saved_msg_count = len(msgs)
                        else:
                            # Incremental: only append new messages since last save
                            new_msgs = msgs[_saved_msg_count:]
                            store.append_session_messages(
                                session_id, new_msgs, metadata_updates=meta,
                            )
                            _saved_msg_count = len(msgs)
                    except Exception as e:
                        logger.error(f"Auto-save session {session_id} failed: {e}")

                content_blocks = []  # initialized before loop to avoid NameError on early break
                _content_saved_this_iter = False

                while iteration < max_iterations:
                    iteration += 1
                    _content_saved_this_iter = False

                    # Check client disconnect or cancellation
                    if cancel_event and cancel_event.is_set():
                        logger.info(f"[Auto] Cancelled at iteration {iteration}")
                        break
                    if request and await request.is_disconnected():
                        logger.warning(f"[Auto] Client disconnected at iteration {iteration}, stopping")
                        break

                    # Send heartbeat between iterations (prevents frontend SSE timeout during context prep)
                    if iteration > 1:
                        yield SSEEventBuilder.heartbeat(0, f"iteration_{iteration}")

                    # === Skill Injection (every iteration - skill may be activated by tool call) ===
                    active_skill = consume_active_skill()
                    if active_skill:
                        skill_block = (
                            f'\n\n<skill name="{active_skill["name"]}">\n'
                            f'{active_skill["instructions"]}\n'
                            f'</skill>\n\n'
                            f'IMPORTANT: You have activated the \'{active_skill["name"]}\' skill.\n'
                            f'Please follow the skill instructions above to complete the user\'s request.\n'
                            f'User\'s original request: {active_skill.get("user_request", "(not specified)")}\n'
                        )
                        system_extra = (system_extra or "") + skill_block
                        logger.info(f"Injected skill '{active_skill['name']}' into system prompt (iteration {iteration})")
                        yield SSEEventBuilder.skill_injected(active_skill["name"])

                    # === MCP Instructions Injection (first iteration only) ===
                    if iteration == 1:
                        from mcp_tools.core import get_mcp_server_instructions
                        mcp_instructions = get_mcp_server_instructions()
                        if mcp_instructions:
                            system_extra = (system_extra or "") + mcp_instructions
                            logger.info(f"Injected MCP server instructions into system prompt ({len(mcp_instructions)} chars)")

                    # === 5-Step Context Protection ===
                    messages_modified = False

                    # Step 1: Truncate old tool results to prevent context overflow
                    tokens_before = count_messages_tokens(messages)
                    messages = prepare_messages_for_api(messages, keep_recent=3)
                    tokens_after = count_messages_tokens(messages)
                    if tokens_before != tokens_after:
                        logger.info(f"[Context] Tool results truncated: {tokens_before:,} -> {tokens_after:,} tokens")
                        messages_modified = True

                    # Step 2: Auto-compact if approaching threshold (structured summary)
                    current_model = body.get("model", "")
                    _ext_ctx = body.get("extended_context")
                    if _ext_ctx is None:
                        _ext_ctx = False
                    model_limits = get_model_limits(current_model, extended_context=_ext_ctx)
                    current_tokens = count_messages_tokens(messages)
                    if should_summarize(messages, model=current_model, extended_context=_ext_ctx):
                        logger.info(f"[Context] Approaching limit ({current_tokens:,}/{model_limits['max_context_tokens']:,} tokens), compacting...")
                        yield SSEEventBuilder.context_compact('approaching_limit', 'haiku', current_tokens)
                        # Send heartbeat before compaction (compaction calls Bedrock and can take 30+ seconds)
                        yield SSEEventBuilder.heartbeat(0, "context_compact")
                        # Pre-compaction memory flush: extract key facts before they're lost
                        try:
                            old_msgs, _ = split_messages_for_summary(messages, model=current_model)
                            if old_msgs:
                                flush_result = await pre_compaction_memory_flush(old_msgs, bedrock_service=bedrock, compact_model=compact_model)
                                if flush_result.get("flushed"):
                                    logger.info(f"[MemoryFlush] Saved {flush_result.get('facts_count', 0)} facts before compaction")
                        except Exception as e:
                            logger.debug(f"[MemoryFlush] Skipped: {e}")
                        try:
                            original_count = len(messages)
                            result = await summarize_context(messages, bedrock_service=bedrock, keep_recent=RECENT_MESSAGES_TO_KEEP, compact_model=compact_model)
                            if result.get("success") and not result.get("skipped"):
                                messages = result["messages"]
                                new_tokens = count_messages_tokens(messages)
                                logger.info(f"[Context] Compacted: {original_count} -> {len(messages)} msgs, {new_tokens:,} tokens")
                                messages_modified = True
                                yield SSEEventBuilder.context_compact_done(original_count, len(messages), new_tokens)
                                # Record summary event
                                if session_id:
                                    summary_text = ""
                                    if messages and messages[0].get("content", "").startswith("[Context Summary"):
                                        summary_text = messages[0].get("content", "")
                                    save_summary_event(session_id, summary_text, original_count, len(messages))
                        except Exception as e:
                            logger.error(f"[Context] Compact failed: {e}")
                            yield SSEEventBuilder.context_compact_failed(str(e))

                    # Step 3: Force aggressive truncation if still critical (95%)
                    current_tokens = count_messages_tokens(messages)
                    if current_tokens > model_limits["max_context_tokens"] * 0.95:
                        logger.warning(f"[Context] Critical ({current_tokens:,}/{model_limits['max_context_tokens']:,} tokens), forcing aggressive truncation")
                        messages = truncate_tool_results(messages, max_size=2048)
                        final_tokens = count_messages_tokens(messages)
                        logger.info(f"[Context] After aggressive truncation: {final_tokens:,} tokens")
                        messages_modified = True

                    # Step 4: Persist changes + notify frontend
                    if messages_modified and session_id:
                        # Save compacted messages (with sync reset + memory re-queue)
                        try:
                            store = get_session_store()
                            store.save_session_complete(session_id, messages, metadata={
                                'compacted': True,
                                'tokens': count_messages_tokens(messages),
                            })
                            # Reset saved count — compaction rewrote the file
                            _saved_msg_count = len(messages)
                            logger.info(f"Session {session_id} persisted with compacted messages (sync reset)")
                        except Exception as e:
                            logger.error(f"Failed to persist compacted session: {e}")

                        # Notify frontend
                        yield SSEEventBuilder.messages_updated(session_id, messages, count_messages_tokens(messages))

                    # Step 5: Repair orphaned tool_use blocks
                    messages = repair_orphan_tool_uses(messages)

                    # Convert request (with skill injection in system prompt)
                    request_body = {**body, "messages": messages}
                    if system_extra:
                        existing_system = request_body.get("system", "")
                        request_body["system"] = (existing_system or "") + system_extra
                    _, bedrock_body = bedrock.convert_request_to_bedrock(
                        request_body,
                        include_tools=bool(tools),
                        tools=[t.model_dump() if hasattr(t, 'model_dump') else t for t in tools] if tools else None,
                        working_dir=working_dir
                    )

                    model_id = bedrock.get_bedrock_model_id(original_model)
                    api_format = bedrock.get_api_format(original_model)

                    # Collect response — track ALL content blocks (text + tool_use)
                    content_blocks = []  # All blocks in order
                    stop_reason = None
                    tool_uses = []
                    _current_block_idx = -1

                    # Stream response (with safety net for token limit errors)
                    _prompt_too_long = False
                    try:
                        async for event in bedrock.invoke_model_stream(model_id, bedrock_body, original_model, api_format=api_format):
                            # Check cancellation during streaming
                            if cancel_event and cancel_event.is_set():
                                logger.info(f"[Auto] Cancelled during Bedrock stream at iteration {iteration}")
                                stop_reason = "cancelled"
                                break
                            yield event

                            # Parse event to track content and tool uses
                            if "data: " in event:
                                try:
                                    data_str = event.split("data: ", 1)[1].strip()
                                    if data_str and data_str != "[DONE]":
                                        data = json.loads(data_str)

                                        if data.get("type") == "content_block_start":
                                            block = data.get("content_block", {})
                                            _current_block_idx = data.get("index", len(content_blocks))
                                            if block.get("type") == "tool_use":
                                                entry = {
                                                    "type": "tool_use",
                                                    "id": block.get("id"),
                                                    "name": block.get("name"),
                                                    "input": {},
                                                }
                                                content_blocks.append(entry)
                                                tool_uses.append(entry)
                                            elif block.get("type") == "text":
                                                content_blocks.append({
                                                    "type": "text",
                                                    "text": "",
                                                })

                                        elif data.get("type") == "content_block_delta":
                                            delta = data.get("delta", {})
                                            if delta.get("type") == "input_json_delta" and tool_uses:
                                                partial = delta.get("partial_json", "")
                                                if partial:
                                                    tool_uses[-1]["_partial_input"] = tool_uses[-1].get("_partial_input", "") + partial
                                            elif delta.get("type") == "text_delta":
                                                text = delta.get("text", "")
                                                if text and content_blocks and content_blocks[-1].get("type") == "text":
                                                    content_blocks[-1]["text"] += text

                                        elif data.get("type") == "message_delta":
                                            delta = data.get("delta", {})
                                            stop_reason = delta.get("stop_reason")
                                except:
                                    pass
                    except Exception as _stream_err:
                        _err_msg = str(_stream_err)
                        if "prompt is too long" in _err_msg or "too many tokens" in _err_msg.lower():
                            logger.warning(f"[Context] Bedrock rejected: {_err_msg}. Forcing emergency compaction...")
                            yield SSEEventBuilder.context_compact('emergency', 'haiku', count_messages_tokens(messages))
                            messages = truncate_tool_results(messages, max_size=2048)
                            try:
                                result = await summarize_context(messages, bedrock_service=bedrock, keep_recent=RECENT_MESSAGES_TO_KEEP, compact_model=compact_model)
                                if result.get("success") and not result.get("skipped"):
                                    messages = result["messages"]
                                    _saved_msg_count = 0  # Reset — messages replaced by compaction
                                    logger.info(f"[Context] Emergency compaction: {len(messages)} msgs, {count_messages_tokens(messages):,} tokens")
                                    yield SSEEventBuilder.context_compact_done(0, len(messages), count_messages_tokens(messages))
                            except Exception as _compact_err:
                                logger.error(f"[Context] Emergency compaction failed: {_compact_err}")
                                yield SSEEventBuilder.context_compact_failed(str(_compact_err))
                            _prompt_too_long = True
                        else:
                            raise  # Re-raise non-token-limit errors

                    if _prompt_too_long:
                        continue  # Retry the iteration with compacted messages

                    # Parse accumulated tool inputs
                    for tool in tool_uses:
                        if "_partial_input" in tool:
                            try:
                                tool["input"] = json.loads(tool.pop("_partial_input"))
                            except:
                                tool["input"] = {}

                    # Check if we need to execute tools (or if cancelled)
                    if stop_reason != "tool_use" or not tool_uses:
                        break
                    if cancel_event and cancel_event.is_set():
                        logger.info(f"[Auto] Cancelled before tool execution at iteration {iteration}")
                        break

                    # Execute tools via MCPManager (parallel with batch SSE events)
                    mcp_manager = await get_mcp_manager()
                    tool_results = []
                    batch_start = asyncio.get_event_loop().time()

                    # Emit batch start event
                    yield SSEEventBuilder.tool_execution_start(tool_uses)

                    # Emit individual tool_start events
                    for tool in tool_uses:
                        yield SSEEventBuilder.tool_start(tool["id"], tool["name"])

                    if msg_request.parallel_tool_execution and len(tool_uses) > 1:
                        # === Parallel execution with heartbeats ===
                        async def _exec_tool_parallel(t, mgr, timeout):
                            t0 = asyncio.get_event_loop().time()
                            try:
                                r = await asyncio.wait_for(
                                    mgr.execute_tool(t["name"], t.get("input", {})),
                                    timeout=timeout
                                )
                                err = "error" in r
                            except asyncio.TimeoutError:
                                r = {"error": f"Tool execution timed out after {timeout}s"}
                                err = True
                            except Exception as e:
                                r = {"error": str(e)}
                                err = True
                            return t, r, err, asyncio.get_event_loop().time() - t0

                        pending = {
                            asyncio.create_task(
                                _exec_tool_parallel(t, mcp_manager, settings.tool_execution_timeout)
                            )
                            for t in tool_uses
                        }

                        _cancelled_tools = False
                        while pending:
                            # Check cancellation — cancel all pending tool tasks
                            if cancel_event and cancel_event.is_set():
                                logger.info(f"[Auto] Cancelling {len(pending)} pending tool task(s)")
                                for p in pending:
                                    p.cancel()
                                # Also kill active subprocesses
                                if session_id:
                                    await mcp_manager.cancel_session_tools(session_id)
                                _cancelled_tools = True
                                break

                            done, pending = await asyncio.wait(
                                pending,
                                timeout=settings.sse_heartbeat_interval,
                                return_when=asyncio.FIRST_COMPLETED,
                            )
                            if not done:
                                # Timeout — send heartbeat
                                elapsed_hb = asyncio.get_event_loop().time() - batch_start
                                yield SSEEventBuilder.heartbeat(elapsed_hb)
                                continue

                            for task in done:
                                tool, result, is_error, elapsed = task.result()
                                logger.info(f"Tool executed: {tool['name']} in {elapsed:.2f}s, error={is_error}")
                                yield SSEEventBuilder.tool_result(
                                    tool["id"], tool["name"], result, is_error, elapsed
                                )
                                result_str = json.dumps(result) if isinstance(result, dict) else str(result)
                                if session_id and len(result_str.encode('utf-8')) > MAX_INLINE_OUTPUT_SIZE:
                                    saved = save_tool_result(session_id, tool["id"], result_str, tool["name"])
                                    if not saved.get("inline"):
                                        logger.info(f"Large tool result saved to file: {tool['name']} ({saved['size']:,} bytes)")
                                        result_str = json.dumps({
                                            "result_truncated": True,
                                            "file_path": saved.get("file_path"),
                                            "size": saved["size"],
                                            "preview": saved.get("preview", result_str[:500]),
                                            "message": f"Result saved to file ({saved['size']:,} bytes).",
                                        })
                                tool_results.append({
                                    "type": "tool_result",
                                    "tool_use_id": tool["id"],
                                    "content": result_str,
                                    "is_error": is_error,
                                })
                        if _cancelled_tools:
                            break
                    else:
                        # === Sequential execution with per-tool heartbeats ===
                        heartbeat_queue = asyncio.Queue()
                        _seq_cancelled = False
                        for tool in tool_uses:
                            # Check cancellation before starting each tool
                            if cancel_event and cancel_event.is_set():
                                logger.info(f"[Auto] Cancelled before executing tool {tool['name']}")
                                if session_id:
                                    await mcp_manager.cancel_session_tools(session_id)
                                _seq_cancelled = True
                                break

                            tool_start_time = asyncio.get_event_loop().time()
                            heartbeat_stop = asyncio.Event()

                            async def _heartbeat_sender(tid, stop_evt, queue, t0):
                                while not stop_evt.is_set():
                                    try:
                                        await asyncio.wait_for(stop_evt.wait(), timeout=settings.sse_heartbeat_interval)
                                        break
                                    except asyncio.TimeoutError:
                                        await queue.put(SSEEventBuilder.heartbeat(asyncio.get_event_loop().time() - t0, tid))

                            hb_task = asyncio.create_task(
                                _heartbeat_sender(tool["id"], heartbeat_stop, heartbeat_queue, tool_start_time)
                            )

                            # Wrap tool execution in a task so we can cancel it
                            _tool_task = asyncio.create_task(
                                asyncio.wait_for(
                                    mcp_manager.execute_tool(tool["name"], tool.get("input", {})),
                                    timeout=settings.tool_execution_timeout,
                                )
                            )

                            try:
                                # Poll for cancellation while tool runs
                                while not _tool_task.done():
                                    if cancel_event and cancel_event.is_set():
                                        logger.info(f"[Auto] Cancelling running tool {tool['name']}")
                                        _tool_task.cancel()
                                        if session_id:
                                            await mcp_manager.cancel_session_tools(session_id)
                                        break
                                    await asyncio.sleep(0.1)

                                if _tool_task.cancelled():
                                    result = {"error": "Tool execution cancelled by user"}
                                    is_error = True
                                    _seq_cancelled = True
                                else:
                                    result = _tool_task.result()
                                    is_error = "error" in result
                            except asyncio.CancelledError:
                                result = {"error": "Tool execution cancelled by user"}
                                is_error = True
                                _seq_cancelled = True
                            except asyncio.TimeoutError:
                                result = {"error": f"Tool execution timed out after {settings.tool_execution_timeout}s"}
                                is_error = True
                            except Exception as e:
                                result = {"error": str(e)}
                                is_error = True

                            heartbeat_stop.set()
                            await hb_task
                            while not heartbeat_queue.empty():
                                yield heartbeat_queue.get_nowait()

                            elapsed = asyncio.get_event_loop().time() - tool_start_time
                            logger.info(f"Tool executed: {tool['name']} in {elapsed:.2f}s, error={is_error}")
                            yield SSEEventBuilder.tool_result(tool["id"], tool["name"], result, is_error, elapsed)

                            result_str = json.dumps(result) if isinstance(result, dict) else str(result)
                            if session_id and len(result_str.encode('utf-8')) > MAX_INLINE_OUTPUT_SIZE:
                                saved = save_tool_result(session_id, tool["id"], result_str, tool["name"])
                                if not saved.get("inline"):
                                    logger.info(f"Large tool result saved to file: {tool['name']} ({saved['size']:,} bytes)")
                                    result_str = json.dumps({
                                        "result_truncated": True,
                                        "file_path": saved.get("file_path"),
                                        "size": saved["size"],
                                        "preview": saved.get("preview", result_str[:500]),
                                        "message": f"Result saved to file ({saved['size']:,} bytes).",
                                    })
                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": tool["id"],
                                "content": result_str,
                                "is_error": is_error,
                            })

                            if _seq_cancelled:
                                break
                        if _seq_cancelled:
                            break

                    # Emit batch complete event
                    batch_elapsed = asyncio.get_event_loop().time() - batch_start
                    yield SSEEventBuilder.tool_execution_complete(len(tool_uses), batch_elapsed)

                    # Record tool usage for auto-unload tracking
                    try:
                        from api.services.session_state import record_tool_usage
                        for t in tool_uses:
                            record_tool_usage(t["name"])
                    except Exception:
                        pass

                    # Build assistant message from ALL content blocks (text + tool_use)
                    assistant_content = []
                    for block in content_blocks:
                        if block.get("type") == "tool_use":
                            assistant_content.append({
                                "type": "tool_use",
                                "id": block["id"],
                                "name": block["name"],
                                "input": block.get("input", {}),
                            })
                        elif block.get("type") == "text" and block.get("text"):
                            assistant_content.append({
                                "type": "text",
                                "text": block["text"],
                            })

                    # Add assistant message and tool results to conversation
                    messages.append({"role": "assistant", "content": assistant_content})
                    messages.append({"role": "user", "content": tool_results})

                    # Auto-save after each tool execution iteration
                    _auto_save_session(messages, {"iteration": iteration})
                    _content_saved_this_iter = True
                    content_blocks = []  # clear so stale blocks aren't re-saved after loop

                    # Break loop if ask_user was called — let user respond
                    if any(t["name"] == "ask_user" for t in tool_uses):
                        logger.info(f"[Auto] ask_user called at iteration {iteration}, yielding for user reply")
                        break

                # Save final assistant response (only for normal end_turn, not after
                # tool-execution saves or cancellation where content_blocks is stale)
                if content_blocks and not _content_saved_this_iter:
                    final_assistant = []
                    for block in content_blocks:
                        if block.get("type") == "text" and block.get("text"):
                            final_assistant.append({"type": "text", "text": block["text"]})
                    if final_assistant:
                        messages.append({"role": "assistant", "content": final_assistant})
                        _auto_save_session(messages)

                # Emit error if max iterations was hit
                if iteration >= max_iterations:
                    yield SSEEventBuilder.error(
                        f"Reached maximum tool iterations ({max_iterations})",
                        error_type="max_iterations"
                    )

                # Send done
                yield SSEEventBuilder.done()

                # Cleanup cancellation event
                if session_id:
                    _cleanup_cancel_event(session_id)

            return create_sse_response(auto_stream_generator(), request)
        
        else:
            # Non-streaming auto execution
            messages = [m.model_dump() if hasattr(m, 'model_dump') else m for m in msg_request.messages]
            iteration = 0
            final_response = None
            system_extra = ""

            while iteration < max_iterations:
                iteration += 1
                messages_modified = False

                # Skill injection (check every iteration - skill may be activated by tool call)
                active_skill = consume_active_skill()
                if active_skill:
                    skill_block = (
                        f'\n\n<skill name="{active_skill["name"]}">\n'
                        f'{active_skill["instructions"]}\n'
                        f'</skill>\n\n'
                        f'IMPORTANT: You have activated the \'{active_skill["name"]}\' skill.\n'
                        f'Please follow the skill instructions above to complete the user\'s request.\n'
                        f'User\'s original request: {active_skill.get("user_request", "(not specified)")}\n'
                    )
                    system_extra = (system_extra or "") + skill_block
                    logger.info(f"Injected skill '{active_skill['name']}' into system prompt (non-streaming, iteration {iteration})")

                # === 5-Step Context Protection (non-streaming) ===
                # Step 1: Truncate old tool results
                messages = prepare_messages_for_api(messages, keep_recent=3)
                # Step 2: Auto-compact if approaching threshold (structured summary)
                ns_model = body.get("model", "")
                _ns_ext_ctx = body.get("extended_context")
                if _ns_ext_ctx is None:
                    _ns_ext_ctx = False
                ns_limits = get_model_limits(ns_model, extended_context=_ns_ext_ctx)
                if should_summarize(messages, model=ns_model, extended_context=_ns_ext_ctx):
                    logger.info(f"[Context] Non-stream compact: {count_messages_tokens(messages):,}/{ns_limits['max_context_tokens']:,} tokens")
                    # Pre-compaction memory flush
                    try:
                        old_msgs, _ = split_messages_for_summary(messages, model=ns_model)
                        if old_msgs:
                            flush_result = await pre_compaction_memory_flush(old_msgs, bedrock_service=bedrock, compact_model=compact_model)
                            if flush_result.get("flushed"):
                                logger.info(f"[MemoryFlush] Saved {flush_result.get('facts_count', 0)} facts before non-stream compaction")
                    except Exception as e:
                        logger.debug(f"[MemoryFlush] Skipped: {e}")
                    try:
                        original_count = len(messages)
                        result = await summarize_context(messages, bedrock_service=bedrock, keep_recent=RECENT_MESSAGES_TO_KEEP, compact_model=compact_model)
                        if result.get("success") and not result.get("skipped"):
                            messages = result["messages"]
                            messages_modified = True
                            # Record summary event
                            if session_id:
                                summary_text = ""
                                if messages and messages[0].get("content", "").startswith("[Context Summary"):
                                    summary_text = messages[0].get("content", "")
                                save_summary_event(session_id, summary_text, original_count, len(messages))
                    except Exception as e:
                        logger.error(f"[Context] Non-stream compact failed: {e}")
                # Step 3: Force aggressive truncation if still critical
                if count_messages_tokens(messages) > ns_limits["max_context_tokens"] * 0.95:
                    messages = truncate_tool_results(messages, max_size=2048)
                    messages_modified = True

                # Step 4: Persist + memory sync (non-streaming)
                if messages_modified and session_id:
                    try:
                        store = get_session_store()
                        store.save_session_complete(session_id, messages, metadata={
                            'compacted': True,
                            'tokens': count_messages_tokens(messages),
                        })
                    except Exception as e:
                        logger.error(f"Failed to persist compacted session: {e}")

                # Step 5: Repair orphaned tool_use
                messages = repair_orphan_tool_uses(messages)

                request_body = {**body, "messages": messages}
                if system_extra:
                    existing_system = request_body.get("system", "")
                    request_body["system"] = (existing_system or "") + system_extra
                _, bedrock_body = bedrock.convert_request_to_bedrock(
                    request_body,
                    include_tools=bool(tools),
                    tools=[t.model_dump() if hasattr(t, 'model_dump') else t for t in tools] if tools else None,
                    working_dir=working_dir
                )

                model_id = bedrock.get_bedrock_model_id(original_model)
                ns_api_format = bedrock.get_api_format(original_model)
                bedrock_response = await bedrock.invoke_model(model_id, bedrock_body, api_format=ns_api_format)

                stop_reason = bedrock_response.get("stop_reason")
                content = bedrock_response.get("content", [])

                # Check for tool uses
                tool_uses = [c for c in content if c.get("type") == "tool_use"]

                if stop_reason != "tool_use" or not tool_uses:
                    final_response = bedrock_response
                    break

                # Execute tools via MCPManager (parallel with timeout)
                mcp_manager = await get_mcp_manager()

                async def _exec_one(t):
                    try:
                        r = await asyncio.wait_for(
                            mcp_manager.execute_tool(t["name"], t.get("input", {})),
                            timeout=settings.tool_execution_timeout
                        )
                        err = "error" in r
                    except asyncio.TimeoutError:
                        r = {"error": f"Tool execution timed out after {settings.tool_execution_timeout}s"}
                        err = True
                    except Exception as e:
                        r = {"error": str(e)}
                        err = True
                    return t["id"], t["name"], r, err

                results_raw = await asyncio.gather(*[_exec_one(t) for t in tool_uses])
                tool_results = []
                for tool_id, tool_name, result, is_error in results_raw:
                    result_str = json.dumps(result) if isinstance(result, dict) else str(result)
                    # Large tool result file storage (non-streaming)
                    if session_id and len(result_str.encode('utf-8')) > MAX_INLINE_OUTPUT_SIZE:
                        saved = save_tool_result(session_id, tool_id, result_str, tool_name)
                        if not saved.get("inline"):
                            logger.info(f"Large tool result saved: {tool_name} ({saved['size']:,} bytes)")
                            result_str = json.dumps({
                                "result_truncated": True,
                                "file_path": saved.get("file_path"),
                                "size": saved["size"],
                                "preview": saved.get("preview", result_str[:500]),
                                "message": f"Result saved to file ({saved['size']:,} bytes).",
                            })
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_id,
                        "content": result_str,
                        "is_error": is_error
                    })

                # Record tool usage for auto-unload tracking (non-streaming)
                try:
                    from api.services.session_state import record_tool_usage
                    for t in tool_uses:
                        record_tool_usage(t.get("name", ""))
                except Exception:
                    pass

                messages.append({"role": "assistant", "content": content})
                messages.append({"role": "user", "content": tool_results})

                # Break loop if ask_user was called — let user respond
                if any(t.get("name") == "ask_user" for t in tool_uses):
                    logger.info(f"[Auto-NS] ask_user called at iteration {iteration}, yielding for user reply")
                    final_response = bedrock_response
                    break

            if final_response is None:
                final_response = {"content": [], "stop_reason": "max_iterations", "usage": {"input_tokens": 0, "output_tokens": 0}}

            # Save final assistant response to messages and persist session
            final_content = final_response.get("content", [])
            if final_content:
                final_assistant = []
                for block in final_content:
                    if block.get("type") == "text" and block.get("text"):
                        final_assistant.append({"type": "text", "text": block["text"]})
                if final_assistant:
                    messages.append({"role": "assistant", "content": final_assistant})
            if session_id:
                try:
                    store = get_session_store()
                    # Check if user has manually set a custom title
                    existing_meta = store.get_session_metadata(session_id)
                    has_custom_title = existing_meta.get("isCustomTitle", False) if existing_meta else False

                    save_meta: dict = {}
                    if has_custom_title:
                        save_meta["title"] = existing_meta.get("title", "Scheduled Task")
                        save_meta["isCustomTitle"] = True
                    else:
                        title = ""
                        # Generate title from first user message
                        for m in messages:
                            c = m.get("content", "") if isinstance(m, dict) else ""
                            role = m.get("role", "") if isinstance(m, dict) else ""
                            if role == "user":
                                if isinstance(c, str):
                                    title = c[:50]
                                elif isinstance(c, list):
                                    for b in c:
                                        if isinstance(b, dict) and b.get("type") == "text":
                                            title = b.get("text", "")[:50]
                                            break
                                break
                        save_meta["title"] = title or "Scheduled Task"
                    save_meta["iteration"] = iteration
                    store.save_session_complete(session_id, messages, metadata=save_meta)
                    logger.info(f"Non-streaming session {session_id} saved with {len(messages)} messages")
                except Exception as e:
                    logger.error(f"Failed to save non-streaming session {session_id}: {e}")

            response = {
                "id": f"msg_{uuid.uuid4().hex[:24]}",
                "type": "message",
                "role": "assistant",
                "content": final_response.get("content", []),
                "model": original_model,
                "stop_reason": final_response.get("stop_reason"),
                "stop_sequence": final_response.get("stop_sequence"),
                "usage": {
                    "input_tokens": final_response.get("usage", {}).get("input_tokens", 0),
                    "output_tokens": final_response.get("usage", {}).get("output_tokens", 0),
                }
            }
            
            return JSONResponse(
                content=response,
                headers={"x-request-id": str(uuid.uuid4())}
            )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Messages Auto API error: {e}")
        raise HTTPException(
            status_code=get_http_status(e),
            detail=eh_format_error(e),
        )


@router.post("/sessions/{session_id}/cancel")
async def cancel_session(session_id: str):
    """Cancel a running streaming session.

    Sets the cancellation event so the auto_stream_generator loop breaks
    at its next check point, and kills any active tool subprocesses.
    """
    evt = _cancel_events.get(session_id)
    killed = 0
    if evt:
        evt.set()
        # Also kill any active tool subprocesses for this session
        try:
            mgr = await get_mcp_manager()
            killed = await mgr.cancel_session_tools(session_id)
        except Exception as e:
            logger.warning(f"[Cancel] Failed to kill tools for {session_id}: {e}")
        logger.info(f"[Cancel] Session {session_id} cancelled by client (killed {killed} subprocess(es))")
        return {"status": "cancelled", "session_id": session_id, "tools_killed": killed}
    # Even without a cancel event, try to kill subprocesses (e.g. from non-streaming calls)
    try:
        mgr = await get_mcp_manager()
        killed = await mgr.cancel_session_tools(session_id)
    except Exception:
        pass
    return {"status": "not_found", "session_id": session_id, "tools_killed": killed}
