"""
Springo UltraPlan Router
深度计划路由 - 多阶段分析、审阅、执行结构化计划
"""
import logging
from typing import Dict, Any
from fastapi import APIRouter, Request, HTTPException

from ..models.requests import PlanGenerateRequest, PlanFeedbackRequest, PlanExecuteRequest
from ..utils.streaming import create_sse_response, format_sse_event, SSEEventBuilder
from ..services.plan_tool import generate_ultraplan, regenerate_section
from ..services.plan_executor import execute_plan

logger = logging.getLogger(__name__)
router = APIRouter()

# In-memory plan storage (MVP)
_plans: Dict[str, Dict[str, Any]] = {}


@router.post("/plans/generate")
async def generate_plan_endpoint(request: Request, body: PlanGenerateRequest):
    """Generate an ultraplan via multi-phase LLM analysis. Returns SSE stream."""

    async def _stream():
        try:
            context_messages = None
            if body.session_id:
                try:
                    from ..services.session_store import get_session_store
                    store = get_session_store()
                    session = store.get_session(body.session_id)
                    if session:
                        context_messages = session.get("messages", [])[-10:]
                except Exception:
                    pass

            yield format_sse_event("plan_generating", {
                "type": "plan_generating",
                "task": body.task_description,
            })

            plan = None
            async for event in generate_ultraplan(
                task_description=body.task_description,
                model=body.model,
                max_tokens=body.max_tokens,
                context_messages=context_messages,
                session_id=body.session_id,
            ):
                phase = event.get("phase")
                status = event.get("status")

                if phase == "analysis" and status == "start":
                    yield format_sse_event("plan_phase", {
                        "type": "plan_phase",
                        "phase": "analysis",
                        "status": "start",
                    })
                elif phase == "analysis" and status == "tool_call":
                    yield format_sse_event("plan_phase", {
                        "type": "plan_phase",
                        "phase": "analysis",
                        "status": "tool_call",
                        "tool_name": event.get("tool_name", ""),
                        "tool_count": event.get("tool_count", 0),
                    })
                elif phase == "analysis" and status == "tool_result":
                    yield format_sse_event("plan_phase", {
                        "type": "plan_phase",
                        "phase": "analysis",
                        "status": "tool_result",
                        "tool_name": event.get("tool_name", ""),
                        "is_error": event.get("is_error", False),
                    })
                elif phase == "analysis" and status == "complete":
                    yield format_sse_event("plan_phase", {
                        "type": "plan_phase",
                        "phase": "analysis",
                        "status": "complete",
                        "content": event.get("content", ""),
                    })
                elif phase == "planning" and status == "start":
                    yield format_sse_event("plan_phase", {
                        "type": "plan_phase",
                        "phase": "planning",
                        "status": "start",
                    })
                elif phase == "planning" and status == "complete":
                    plan = event["plan"]
                elif phase in ("analysis", "planning") and status == "error":
                    yield format_sse_event("plan_phase", {
                        "type": "plan_phase",
                        "phase": phase,
                        "status": "error",
                        "error": event.get("error", ""),
                    })

            if plan:
                if body.session_id:
                    plan["session_id"] = body.session_id
                _plans[plan["id"]] = plan
                yield SSEEventBuilder.plan_generated(plan)

            yield SSEEventBuilder.done()

        except Exception as e:
            logger.error(f"UltraPlan generation failed: {e}")
            yield SSEEventBuilder.error(str(e))
            yield SSEEventBuilder.done()

    return create_sse_response(_stream(), request)


@router.get("/plans/{plan_id}")
async def get_plan(plan_id: str):
    """Get a plan by ID."""
    plan = _plans.get(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    return plan


@router.post("/plans/{plan_id}/feedback")
async def plan_feedback(request: Request, plan_id: str, body: PlanFeedbackRequest):
    """Submit feedback on a plan section. For 'reject', regenerates the section via SSE."""
    plan = _plans.get(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")

    # Find section
    section = None
    section_idx = None
    for i, s in enumerate(plan.get("sections", [])):
        if s["id"] == body.section_id:
            section = s
            section_idx = i
            break

    if section is None:
        raise HTTPException(status_code=404, detail="Section not found")

    if body.action == "approve":
        section["status"] = "approved"
        section["feedback"] = body.feedback
        plan["sections"][section_idx] = section

        # Check if all sections approved
        if all(s["status"] == "approved" for s in plan["sections"]):
            plan["status"] = "approved"

        return {"ok": True, "section": section, "plan_status": plan["status"]}

    elif body.action == "reject":
        section["status"] = "rejected"
        section["feedback"] = body.feedback

        if body.feedback:
            # Regenerate section with feedback via SSE
            async def _stream():
                try:
                    yield format_sse_event("plan_section_regenerating", {
                        "type": "plan_section_regenerating",
                        "plan_id": plan_id,
                        "section_id": body.section_id,
                    })

                    updated = await regenerate_section(
                        plan=plan,
                        section_id=body.section_id,
                        feedback=body.feedback,
                    )

                    # Update stored plan
                    plan["sections"][section_idx] = updated

                    yield SSEEventBuilder.plan_section_update(plan_id, updated)
                    yield SSEEventBuilder.done()

                except Exception as e:
                    logger.error(f"Section regen failed: {e}")
                    yield SSEEventBuilder.error(str(e))
                    yield SSEEventBuilder.done()

            return create_sse_response(_stream(), request)

        plan["sections"][section_idx] = section
        return {"ok": True, "section": section}

    elif body.action == "comment":
        section["feedback"] = body.feedback
        plan["sections"][section_idx] = section
        return {"ok": True, "section": section}

    raise HTTPException(status_code=400, detail=f"Unknown action: {body.action}")


@router.post("/plans/{plan_id}/approve-all")
async def approve_all_sections(plan_id: str):
    """Approve all pending sections."""
    plan = _plans.get(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")

    for s in plan["sections"]:
        if s["status"] == "pending":
            s["status"] = "approved"

    plan["status"] = "approved"
    return {"ok": True, "plan": plan}


@router.post("/plans/{plan_id}/execute")
async def execute_plan_endpoint(request: Request, plan_id: str, body: PlanExecuteRequest):
    """Execute all approved sections of a plan. Returns SSE stream."""
    plan = _plans.get(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")

    approved = [s for s in plan["sections"] if s["status"] == "approved"]
    if not approved:
        raise HTTPException(status_code=400, detail="No approved sections to execute")

    plan["status"] = "executing"

    return create_sse_response(execute_plan(plan, body.session_id), request)


@router.delete("/plans/{plan_id}")
async def delete_plan(plan_id: str):
    """Delete a plan."""
    if plan_id in _plans:
        del _plans[plan_id]
    return {"ok": True}


@router.get("/plans")
async def list_plans():
    """List all plans."""
    return {"plans": list(_plans.values())}
