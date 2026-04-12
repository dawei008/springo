"""
Springo Plan Executor Service
计划执行器 - 按 section 执行已批准的计划
"""
import logging
import asyncio
from typing import AsyncGenerator, Dict, Any
from datetime import datetime

from ..utils.streaming import format_sse_event

logger = logging.getLogger(__name__)


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
            # Build execution prompt from section steps
            steps_text = "\n".join(f"- {s}" for s in section.get("steps", []))
            exec_prompt = (
                f"Execute this plan section:\n\n"
                f"## {section.get('title', '')}\n"
                f"{section.get('description', '')}\n\n"
                f"Steps:\n{steps_text}\n\n"
                f"Execute each step using the available tools. Be direct and concise."
            )

            # Send to the auto-messages endpoint internally
            from .vendor_router import get_vendor_router
            from .tool_manager import get_tool_manager

            router = get_vendor_router()
            tool_manager = await get_tool_manager()
            tool_defs = tool_manager.get_tool_definitions()

            messages = [{"role": "user", "content": exec_prompt}]

            # Stream the LLM response for this section
            collected_text = ""
            async for chunk in router.stream_with_tools(
                messages=messages,
                model="claude-sonnet-4-6",
                max_tokens=8192,
                tools=tool_defs,
                tool_manager=tool_manager,
                session_id=session_id,
            ):
                # Forward streaming events with section context
                yield format_sse_event("plan_section_delta", {
                    "type": "plan_section_delta",
                    "plan_id": plan_id,
                    "section_id": section_id,
                    "chunk": chunk if isinstance(chunk, str) else str(chunk),
                })

            section["status"] = "completed"
            section["result"] = "Completed successfully"

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
