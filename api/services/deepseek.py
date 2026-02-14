"""
DeepSeek Direct API Service
Calls api.deepseek.com (OpenAI-compatible) instead of Bedrock.
"""
import json
import uuid
import logging
import copy
from typing import AsyncGenerator, Dict, Any, Optional
from datetime import datetime

import httpx

from ..config import settings
from .model_registry import (
    get_model_info,
    get_vendor_model_id,
    get_max_tools,
    model_supports_tools,
)
from .bedrock import (
    COMMON_SYSTEM_PROMPT,
    _prioritize_tools,
    _get_system_prompt_for_model,
)

logger = logging.getLogger(__name__)


class DeepSeekService:
    """Direct DeepSeek API service using httpx (OpenAI-compatible)."""

    def __init__(self, api_key: str, base_url: str = "https://api.deepseek.com"):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            timeout=httpx.Timeout(connect=60.0, read=600.0, write=60.0, pool=60.0),
        )

    async def close(self):
        await self._client.aclose()

    def update_api_key(self, api_key: str):
        """Update the API key (after user configures it via settings)."""
        self.api_key = api_key
        self._client.headers["Authorization"] = f"Bearer {api_key}"

    # ------------------------------------------------------------------
    # Request conversion: Anthropic format -> OpenAI format
    # ------------------------------------------------------------------

    def convert_request(
        self,
        request: Dict[str, Any],
        include_tools: bool = True,
        tools: list = None,
        working_dir: str = None,
    ) -> tuple[str, Dict[str, Any]]:
        """Convert Anthropic-format request to OpenAI-format body.

        Returns (vendor_model_id, openai_body).
        """
        model = request.get("model", "deepseek-v3.2-direct")
        vendor_model_id = get_vendor_model_id(model)

        # Build system prompt
        from ..utils.springo_md import load_springo_md
        system_prompt = request.get("system") or _get_system_prompt_for_model(model)
        springo_md = load_springo_md()
        if springo_md:
            system_prompt = system_prompt.replace("{SPRINGO_MD_PLACEHOLDER}", springo_md)
        else:
            system_prompt = system_prompt.replace("{SPRINGO_MD_PLACEHOLDER}", "")
        if working_dir:
            import os
            springo_config_dir = os.path.expanduser("~/.springo")
            system_prompt += (
                f"\n\n## Working Directory & Springo Config\n"
                f"- **Working Directory**: `{working_dir}` -- project code lives here\n"
                f"- **Springo Config**: `{springo_config_dir}/` -- settings, skills, sessions, scripts\n"
                f"  - Skills: `{springo_config_dir}/skills/` (each subfolder has SKILL.md)\n"
                f"  - Config: `{springo_config_dir}/config.json`\n"
                f"- For `glob`/`grep`: use `path` parameter to search the right directory\n"
                f"  - Project files: `path: \"{working_dir}\"`\n"
                f"  - Skills/config: `path: \"{springo_config_dir}\"`\n"
            )

        # Convert messages
        openai_messages = [{"role": "system", "content": system_prompt}]
        src_messages = copy.deepcopy(request.get("messages", []))

        # Inject current time into last user message
        if src_messages:
            now = datetime.now()
            weekday_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
            weekday = weekday_names[now.weekday()]
            time_str = now.strftime('%Y-%m-%d %H:%M')
            time_prefix = f"[Current time: {time_str} ({weekday})]\n\n"
            for i in range(len(src_messages) - 1, -1, -1):
                msg = src_messages[i]
                if msg.get("role") == "user":
                    content = msg.get("content", "")
                    if isinstance(content, str):
                        src_messages[i]["content"] = time_prefix + content
                    elif isinstance(content, list) and content:
                        if content[0].get("type") == "text":
                            content[0]["text"] = time_prefix + content[0].get("text", "")
                    break

        for msg in src_messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")

            if role == "assistant":
                openai_msg = self._convert_assistant_message(content)
                openai_messages.append(openai_msg)
            elif role == "user":
                # User content may contain tool_result blocks
                if isinstance(content, list):
                    has_tool_results = any(
                        isinstance(b, dict) and b.get("type") == "tool_result"
                        for b in content
                    )
                    if has_tool_results:
                        # Convert tool_result blocks to OpenAI tool messages
                        text_parts = []
                        for block in content:
                            if isinstance(block, dict):
                                if block.get("type") == "tool_result":
                                    # Flush any accumulated text first
                                    if text_parts:
                                        openai_messages.append({
                                            "role": "user",
                                            "content": "\n".join(text_parts),
                                        })
                                        text_parts = []
                                    result_content = block.get("content", "")
                                    if isinstance(result_content, list):
                                        parts = []
                                        for rb in result_content:
                                            if isinstance(rb, dict) and rb.get("type") == "text":
                                                parts.append(rb.get("text", ""))
                                            elif isinstance(rb, str):
                                                parts.append(rb)
                                            else:
                                                parts.append(json.dumps(rb))
                                        result_content = "\n".join(parts)
                                    openai_messages.append({
                                        "role": "tool",
                                        "tool_call_id": block.get("tool_use_id", ""),
                                        "content": str(result_content),
                                    })
                                elif block.get("type") == "text":
                                    text_parts.append(block.get("text", ""))
                            elif isinstance(block, str):
                                text_parts.append(block)
                        if text_parts:
                            openai_messages.append({
                                "role": "user",
                                "content": "\n".join(text_parts),
                            })
                    else:
                        # Regular user message with content blocks
                        text = self._extract_text_from_content(content)
                        openai_messages.append({"role": "user", "content": text})
                elif isinstance(content, str):
                    openai_messages.append({"role": "user", "content": content})
                else:
                    openai_messages.append({"role": "user", "content": str(content)})

        # Build body — clamp max_tokens to model limit
        model_info = get_model_info(model)
        model_max_output = model_info.get("max_output", 8192) if model_info else 8192
        req_max_tokens = request.get("max_tokens", 8192)
        clamped_max_tokens = min(req_max_tokens, model_max_output)

        body: Dict[str, Any] = {
            "model": vendor_model_id,
            "messages": openai_messages,
            "max_tokens": clamped_max_tokens,
            "_original_model": model,  # Used by VendorRouter to dispatch invoke_model
        }

        # Optional parameters
        if "temperature" in request and request["temperature"] is not None:
            body["temperature"] = request["temperature"]
        if "top_p" in request and request["top_p"] is not None:
            body["top_p"] = request["top_p"]
        if "stop_sequences" in request and request["stop_sequences"]:
            body["stop"] = request["stop_sequences"]

        # Convert tools
        if include_tools and model_supports_tools(model):
            raw_tools = request.get("tools") or tools or []
            if raw_tools:
                max_t = get_max_tools(model)
                if max_t > 0 and len(raw_tools) > max_t:
                    raw_tools = _prioritize_tools(raw_tools, max_t)
                body["tools"] = self._convert_tools(raw_tools)

                # tool_choice mapping
                tool_choice = request.get("tool_choice")
                if tool_choice:
                    tc_type = tool_choice.get("type", "auto") if isinstance(tool_choice, dict) else tool_choice
                    if tc_type == "any":
                        body["tool_choice"] = "required"
                    elif tc_type == "tool":
                        body["tool_choice"] = {
                            "type": "function",
                            "function": {"name": tool_choice.get("name", "")},
                        }
                    else:
                        body["tool_choice"] = "auto"

        return vendor_model_id, body

    def _convert_assistant_message(self, content) -> Dict[str, Any]:
        """Convert Anthropic assistant content to OpenAI assistant message."""
        if isinstance(content, str):
            return {"role": "assistant", "content": content}

        if isinstance(content, list):
            text_parts = []
            tool_calls = []
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "text":
                        text_parts.append(block.get("text", ""))
                    elif block.get("type") == "tool_use":
                        tool_calls.append({
                            "id": block.get("id", ""),
                            "type": "function",
                            "function": {
                                "name": block.get("name", ""),
                                "arguments": json.dumps(block.get("input", {})),
                            },
                        })

            msg: Dict[str, Any] = {"role": "assistant"}
            if text_parts:
                msg["content"] = "\n".join(text_parts)
            else:
                msg["content"] = None
            if tool_calls:
                msg["tool_calls"] = tool_calls
            return msg

        return {"role": "assistant", "content": str(content)}

    @staticmethod
    def _extract_text_from_content(content: list) -> str:
        """Extract text from Anthropic content blocks."""
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                if block.get("type") == "text":
                    parts.append(block.get("text", ""))
        return "\n".join(parts) if parts else ""

    @staticmethod
    def _convert_tools(tools: list) -> list:
        """Convert Anthropic tool definitions to OpenAI function format."""
        openai_tools = []
        for tool in tools:
            openai_tools.append({
                "type": "function",
                "function": {
                    "name": tool.get("name", ""),
                    "description": tool.get("description", ""),
                    "parameters": tool.get("input_schema", tool.get("inputSchema", {})),
                },
            })
        return openai_tools

    # ------------------------------------------------------------------
    # Response conversion: OpenAI format -> Anthropic format
    # ------------------------------------------------------------------

    @staticmethod
    def _convert_stop_reason(finish_reason: str) -> str:
        mapping = {
            "stop": "end_turn",
            "tool_calls": "tool_use",
            "length": "max_tokens",
        }
        return mapping.get(finish_reason, "end_turn")

    @staticmethod
    def _openai_response_to_anthropic(data: dict, model: str) -> dict:
        """Convert a non-streaming OpenAI response to Anthropic format."""
        choice = data.get("choices", [{}])[0]
        message = choice.get("message", {})
        finish_reason = choice.get("finish_reason", "stop")

        content_blocks = []
        if message.get("content"):
            content_blocks.append({"type": "text", "text": message["content"]})
        if message.get("tool_calls"):
            for tc in message["tool_calls"]:
                fn = tc.get("function", {})
                try:
                    args = json.loads(fn.get("arguments", "{}"))
                except (json.JSONDecodeError, TypeError):
                    args = {}
                content_blocks.append({
                    "type": "tool_use",
                    "id": tc.get("id", f"tooluse_{uuid.uuid4().hex[:24]}"),
                    "name": fn.get("name", ""),
                    "input": args,
                })

        usage = data.get("usage", {})
        return {
            "content": content_blocks,
            "stop_reason": DeepSeekService._convert_stop_reason(finish_reason),
            "usage": {
                "input_tokens": usage.get("prompt_tokens", 0),
                "output_tokens": usage.get("completion_tokens", 0),
            },
        }

    # ------------------------------------------------------------------
    # API calls
    # ------------------------------------------------------------------

    async def invoke_model(
        self,
        model_id: str,
        body: Dict[str, Any],
        max_retries: int = 3,
        api_format: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Non-streaming call to DeepSeek API.

        Returns Anthropic-shaped response dict.
        """
        import random

        body.pop("_original_model", None)
        body["stream"] = False

        for attempt in range(max_retries):
            try:
                response = await self._client.post(
                    "/chat/completions",
                    json=body,
                )
                if response.status_code != 200:
                    error_text = response.text[:500]
                    logger.error(f"DeepSeek API {response.status_code}: {error_text}")
                    if response.status_code == 429 and attempt < max_retries - 1:
                        backoff = min(2 ** attempt + random.random(), 5)
                        logger.warning(f"DeepSeek 429 throttled (attempt {attempt + 1}/{max_retries}), retrying in {backoff:.1f}s...")
                        import asyncio
                        await asyncio.sleep(backoff)
                        continue
                    response.raise_for_status()
                data = response.json()
                original_model = body.get("_original_model", model_id)
                return self._openai_response_to_anthropic(data, original_model)
            except httpx.HTTPStatusError as e:
                raise
            except Exception as e:
                if attempt < max_retries - 1:
                    logger.warning(f"DeepSeek invoke error (attempt {attempt + 1}/{max_retries}): {e}")
                    import asyncio
                    await asyncio.sleep(1)
                    continue
                raise

    async def invoke_model_stream(
        self,
        model_id: str,
        body: Dict[str, Any],
        original_model: str,
        max_retries: int = 3,
        api_format: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """Streaming call to DeepSeek API.

        Yields SSE-formatted strings in Anthropic format (identical to
        BedrockService.invoke_model_stream output).
        """
        import random

        body.pop("_original_model", None)
        body["stream"] = True
        body["stream_options"] = {"include_usage": True}

        message_id = f"msg_{uuid.uuid4().hex[:24]}"
        current_block_index = -1
        started_message = False
        # Track tool calls being built incrementally
        _tool_calls: Dict[int, Dict[str, Any]] = {}  # index -> {id, name, arguments}
        _current_text_block_open = False
        _has_content = False
        _finish_reason_received = False
        _last_finish_reason = None

        for attempt in range(max_retries):
            try:
                async with self._client.stream(
                    "POST",
                    "/chat/completions",
                    json=body,
                ) as response:
                    if response.status_code != 200:
                        error_body = await response.aread()
                        error_text = error_body.decode("utf-8", errors="replace")[:500]
                        logger.error(f"DeepSeek stream API {response.status_code}: {error_text}")
                    response.raise_for_status()

                    async for line in response.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        data_str = line[6:].strip()
                        if data_str == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data_str)
                        except json.JSONDecodeError:
                            continue

                        # Emit message_start on first chunk
                        if not started_message:
                            started_message = True
                            msg = {
                                "id": message_id,
                                "type": "message",
                                "role": "assistant",
                                "content": [],
                                "model": original_model,
                                "stop_reason": None,
                                "stop_sequence": None,
                                "usage": {"input_tokens": 0, "output_tokens": 0},
                            }
                            yield f"event: message_start\ndata: {json.dumps({'type': 'message_start', 'message': msg})}\n\n"

                        choices = chunk.get("choices", [])
                        usage = chunk.get("usage")

                        if choices:
                            choice = choices[0]
                            delta = choice.get("delta", {})
                            finish_reason = choice.get("finish_reason")

                            # Text content
                            if delta.get("content") is not None:
                                text = delta["content"]
                                if text:
                                    if not _current_text_block_open:
                                        current_block_index += 1
                                        _current_text_block_open = True
                                        _has_content = True
                                        yield f"event: content_block_start\ndata: {json.dumps({'type': 'content_block_start', 'index': current_block_index, 'content_block': {'type': 'text', 'text': ''}})}\n\n"
                                    yield f"event: content_block_delta\ndata: {json.dumps({'type': 'content_block_delta', 'index': current_block_index, 'delta': {'type': 'text_delta', 'text': text}})}\n\n"

                            # Tool calls (streamed incrementally)
                            if delta.get("tool_calls"):
                                # Close text block if open
                                if _current_text_block_open:
                                    yield f"event: content_block_stop\ndata: {json.dumps({'type': 'content_block_stop', 'index': current_block_index})}\n\n"
                                    _current_text_block_open = False

                                for tc_delta in delta["tool_calls"]:
                                    tc_index = tc_delta.get("index", 0)
                                    if tc_index not in _tool_calls:
                                        # New tool call — emit content_block_start
                                        tc_id = tc_delta.get("id", f"tooluse_{uuid.uuid4().hex[:24]}")
                                        fn = tc_delta.get("function", {})
                                        tc_name = fn.get("name", "")
                                        _tool_calls[tc_index] = {
                                            "id": tc_id,
                                            "name": tc_name,
                                            "arguments": "",
                                        }
                                        current_block_index += 1
                                        _has_content = True
                                        cb = {
                                            "type": "tool_use",
                                            "id": tc_id,
                                            "name": tc_name,
                                            "input": {},
                                        }
                                        yield f"event: content_block_start\ndata: {json.dumps({'type': 'content_block_start', 'index': current_block_index, 'content_block': cb})}\n\n"
                                    else:
                                        fn = tc_delta.get("function", {})

                                    # Accumulate arguments
                                    args_chunk = fn.get("arguments", "")
                                    if args_chunk:
                                        _tool_calls[tc_index]["arguments"] += args_chunk
                                        yield f"event: content_block_delta\ndata: {json.dumps({'type': 'content_block_delta', 'index': current_block_index, 'delta': {'type': 'input_json_delta', 'partial_json': args_chunk}})}\n\n"

                            # Handle finish
                            if finish_reason:
                                _finish_reason_received = True
                                _last_finish_reason = finish_reason
                                logger.info(f"DeepSeek stream finish_reason={finish_reason}, model={original_model}")
                                # Close text block if open
                                if _current_text_block_open:
                                    yield f"event: content_block_stop\ndata: {json.dumps({'type': 'content_block_stop', 'index': current_block_index})}\n\n"
                                    _current_text_block_open = False
                                # Close any open tool call blocks
                                for tc_idx in sorted(_tool_calls.keys()):
                                    yield f"event: content_block_stop\ndata: {json.dumps({'type': 'content_block_stop', 'index': current_block_index})}\n\n"

                        # Usage chunk (arrives with stream_options.include_usage)
                        if usage:
                            stop_reason = self._convert_stop_reason(
                                _last_finish_reason or (choices[0].get("finish_reason", "stop") if choices else "stop")
                            )
                            delta_data = {
                                "type": "message_delta",
                                "delta": {"stop_reason": stop_reason, "stop_sequence": None},
                                "usage": {"output_tokens": usage.get("completion_tokens", 0)},
                            }
                            yield f"event: message_delta\ndata: {json.dumps(delta_data)}\n\n"

                    if not _finish_reason_received and started_message:
                        logger.warning(
                            f"DeepSeek stream ended WITHOUT finish_reason — possible incomplete response "
                            f"(model={original_model}, blocks={current_block_index + 1}, text_open={_current_text_block_open})"
                        )
                        # Close any unclosed blocks so the Anthropic-format stream is well-formed
                        if _current_text_block_open:
                            yield f"event: content_block_stop\ndata: {json.dumps({'type': 'content_block_stop', 'index': current_block_index})}\n\n"
                        # Emit message_delta with stop_reason so downstream knows it ended
                        delta_data = {
                            "type": "message_delta",
                            "delta": {"stop_reason": "end_turn", "stop_sequence": None},
                            "usage": {"output_tokens": 0},
                        }
                        yield f"event: message_delta\ndata: {json.dumps(delta_data)}\n\n"

                    if not started_message:
                        msg = {
                            "id": message_id,
                            "type": "message",
                            "role": "assistant",
                            "content": [],
                            "model": original_model,
                            "stop_reason": None,
                            "stop_sequence": None,
                            "usage": {"input_tokens": 0, "output_tokens": 0},
                        }
                        yield f"event: message_start\ndata: {json.dumps({'type': 'message_start', 'message': msg})}\n\n"
                    yield f"event: message_stop\ndata: {json.dumps({'type': 'message_stop'})}\n\n"
                    return  # Success

            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429 and attempt < max_retries - 1:
                    backoff = min(2 ** attempt + random.random(), 5)
                    logger.warning(f"DeepSeek stream 429 (attempt {attempt + 1}/{max_retries}), retrying in {backoff:.1f}s...")
                    import asyncio
                    await asyncio.sleep(backoff)
                    continue
                error_data = {
                    "type": "error",
                    "error": {"type": "api_error", "message": str(e)},
                }
                yield f"event: error\ndata: {json.dumps(error_data)}\n\n"
                return
            except Exception as e:
                logger.error(f"DeepSeek stream error: {e}")
                error_data = {
                    "type": "error",
                    "error": {"type": "api_error", "message": str(e)},
                }
                yield f"event: error\ndata: {json.dumps(error_data)}\n\n"
                return

    async def invoke_model_stream_text(
        self,
        model_id: str,
        body: Dict[str, Any],
        max_retries: int = 3,
        api_format: Optional[str] = None,
    ) -> AsyncGenerator[dict, None]:
        """Simple dict streaming for agent team use.

        Yields: {"type": "delta", "text": "..."} and {"type": "usage", ...}
        """
        body.pop("_original_model", None)
        body["stream"] = True
        body["stream_options"] = {"include_usage": True}

        async with self._client.stream(
            "POST",
            "/chat/completions",
            json=body,
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line.startswith("data: "):
                    continue
                data_str = line[6:].strip()
                if data_str == "[DONE]":
                    break
                try:
                    chunk = json.loads(data_str)
                except json.JSONDecodeError:
                    continue

                choices = chunk.get("choices", [])
                usage = chunk.get("usage")

                if choices:
                    delta = choices[0].get("delta", {})
                    text = delta.get("content")
                    if text:
                        yield {"type": "delta", "text": text}

                if usage:
                    yield {
                        "type": "usage",
                        "input_tokens": usage.get("prompt_tokens", 0),
                        "output_tokens": usage.get("completion_tokens", 0),
                    }

    # ------------------------------------------------------------------
    # Convenience: match BedrockService interface names
    # ------------------------------------------------------------------

    def convert_request_to_bedrock(self, *args, **kwargs):
        """Alias for convert_request (matches BedrockService interface)."""
        return self.convert_request(*args, **kwargs)

    def get_bedrock_model_id(self, model: str) -> str:
        """Return the vendor model ID (matches BedrockService interface)."""
        return get_vendor_model_id(model)

    @staticmethod
    def get_api_format(model: str) -> str:
        """Return 'openai' for DeepSeek models."""
        info = get_model_info(model)
        return info["api_format"] if info else "openai"


# Singleton
_deepseek_service: Optional[DeepSeekService] = None


def get_deepseek_service() -> Optional[DeepSeekService]:
    """Get the DeepSeek service singleton (None if not configured)."""
    return _deepseek_service


def init_deepseek_service(api_key: str, base_url: str = "https://api.deepseek.com") -> DeepSeekService:
    """Initialize or reinitialize the DeepSeek service."""
    global _deepseek_service
    if _deepseek_service:
        _deepseek_service.update_api_key(api_key)
    else:
        _deepseek_service = DeepSeekService(api_key, base_url)
    return _deepseek_service
