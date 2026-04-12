"""
Springo Plan Executor Service
计划执行器 - 按 section 执行已批准的计划，支持工具调用循环
"""
import json
import logging
import asyncio
from typing import AsyncGenerator, Dict, Any, List
from datetime import datetime

from ..utils.streaming import format_sse_event

logger = logging.getLogger(__name__)

MAX_TOOL_ITERATIONS = 20


async def _execute_section(
    section: Dict[str, Any],
    session_id: str,
    model: str = "claude-sonnet-4-6",
) -> AsyncGenerator[Dict[str, Any], None]:
    """Execute a single section with tool loop. Yields dicts with type + content."""
    from .vendor_router import get_vendor_router
    from .tool_manager import get_tool_manager

    router = get_vendor_router()
    tool_manager = await get_tool_manager()
    tool_defs = tool_manager.get_tool_definitions()

    steps_text = "\n".join(f"- {s}" for s in section.get("steps", []))
    exec_prompt = (
        f"Execute this plan section:\n\n"
        f"## {section.get('title', '')}\n"
        f"{section.get('description', '')}\n\n"
        f"Steps:\n{steps_text}\n\n"
        f"Execute each step using the available tools. Be direct and concise."
    )

    messages: List[Dict[str, Any]] = [{"role": "user", "content": exec_prompt}]

    for iteration in range(MAX_TOOL_ITERATIONS):
        # Build request and call LLM
        request_body = {
            "model": model,
            "messages": messages,
            "max_tokens": 8192,
            "system": "You are executing a plan section. Use the provided tools to complete each step.",
        }

        tools_raw = [t.model_dump() if hasattr(t, "model_dump") else t for t in tool_defs] if tool_defs else None
        model_id, bedrock_body = router.convert_request_to_bedrock(
            request_body,
            include_tools=bool(tools_raw),
            tools=tools_raw,
        )

        response = await router.invoke_model(model_id, bedrock_body)

        # Parse response content
        content_blocks = response.get("content", [])
        stop_reason = response.get("stop_reason", "end_turn")
        text_parts = []
        tool_uses = []

        for block in content_blocks:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    text_parts.append(block.get("text", ""))
                elif block.get("type") == "tool_use":
                    tool_uses.append(block)

        # Yield text output
        combined_text = "".join(text_parts)
        if combined_text:
            yield {"type": "text", "content": combined_text}

        # If no tool calls, we're done
        if not tool_uses or stop_reason != "tool_use":
            break

        # Execute tools
        assistant_msg = {"role": "assistant", "content": content_blocks}
        messages.append(assistant_msg)

        tool_results = []
        for tool in tool_uses:
            tool_name = tool.get("name", "")
            tool_input = tool.get("input", {})
            tool_id = tool.get("id", "")

            yield {"type": "tool_call", "name": tool_name, "input": tool_input}

            try:
                result = await asyncio.wait_for(
                    tool_manager.execute_tool(tool_name, tool_input, session_id=session_id),
                    timeout=120,
                )
                result_content = result.get("content", "") if isinstance(result, dict) else str(result)
                is_error = result.get("is_error", False) if isinstance(result, dict) else False
            except asyncio.TimeoutError:
                result_content = f"Tool {tool_name} timed out after 120s"
                is_error = True
            except Exception as e:
                result_content = f"Tool {tool_name} failed: {e}"
                is_error = True

            yield {"type": "tool_result", "name": tool_name, "content": str(result_content)[:500], "is_error": is_error}

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tool_id,
                "content": str(result_content),
                "is_error": is_error,
            })

        messages.append({"role": "user", "content": tool_results})


async def execute_plan(
    plan: Dict[str, Any],
    session_id: str,
) -> AsyncGenerator[str, None]:
    """Execute approved plan sections sequentially, yielding SSE events."""

    plan_id = plan["id"]
    approved = [s for s in plan.get("sections", []) if s["status"] == "approved"]

    if not approved:
        yield format_sse_event("plan_error", {
            "type": "plan_error",
            "plan_id": plan_id,
            "error": "No approved sections to execute",
        })
        return

    yield format_sse_event("plan_execution_start", {
        "type": "plan_execution_start",
        "plan_id": plan_id,
        "total_sections": len(approved),
        "timestamp": datetime.now().isoformat(),
    })

    for section in approved:
        section_id = section["id"]
        section["status"] = "in_progress"

        yield format_sse_event("plan_section_start", {
            "type": "plan_section_start",
            "plan_id": plan_id,
            "section_id": section_id,
            "title": section.get("title", ""),
            "timestamp": datetime.now().isoformat(),
        })

        try:
            collected_text = ""
            async for event in _execute_section(section, session_id):
                event_type = event.get("type")

                if event_type == "text":
                    collected_text += event["content"]
                    yield format_sse_event("plan_section_delta", {
                        "type": "plan_section_delta",
                        "plan_id": plan_id,
                        "section_id": section_id,
                        "delta_type": "text",
                        "content": event["content"],
                    })
                elif event_type == "tool_call":
                    yield format_sse_event("plan_section_delta", {
                        "type": "plan_section_delta",
                        "plan_id": plan_id,
                        "section_id": section_id,
                        "delta_type": "tool_call",
                        "tool_name": event["name"],
                    })
                elif event_type == "tool_result":
                    yield format_sse_event("plan_section_delta", {
                        "type": "plan_section_delta",
                        "plan_id": plan_id,
                        "section_id": section_id,
                        "delta_type": "tool_result",
                        "tool_name": event["name"],
                        "content": event["content"],
                        "is_error": event.get("is_error", False),
                    })

            section["status"] = "completed"
            section["result"] = collected_text[:500] if collected_text else "Completed successfully"

            yield format_sse_event("plan_section_complete", {
                "type": "plan_section_complete",
                "plan_id": plan_id,
                "section_id": section_id,
                "success": True,
                "timestamp": datetime.now().isoformat(),
            })

        except Exception as e:
            logger.error(f"Section {section_id} execution failed: {e}")
            section["status"] = "failed"
            section["result"] = str(e)

            yield format_sse_event("plan_section_complete", {
                "type": "plan_section_complete",
                "plan_id": plan_id,
                "section_id": section_id,
                "success": False,
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            })

    # Update plan status
    all_completed = all(s["status"] == "completed" for s in approved)
    plan["status"] = "completed" if all_completed else "failed"

    yield format_sse_event("plan_execution_complete", {
        "type": "plan_execution_complete",
        "plan_id": plan_id,
        "success": all_completed,
        "timestamp": datetime.now().isoformat(),
    })
