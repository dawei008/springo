"""
Springo UltraPlan Generation Service
深度计划服务 - 多阶段分析 → 结构化执行计划
"""
import json
import uuid
import logging
from typing import Optional, List, Dict, Any, AsyncGenerator
from datetime import datetime

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Phase 1: Deep Analysis — free-form reasoning about task, risks, dependencies
# ---------------------------------------------------------------------------

ANALYSIS_SYSTEM_PROMPT = """You are a senior technical architect performing deep analysis before creating an execution plan.

Given a task description (and optional conversation context), produce a thorough analysis covering:

1. **Requirements Decomposition** — break the task into its fundamental components
2. **Dependency Graph** — which components must come before others and why
3. **Risk Assessment** — what could go wrong, edge cases, failure modes
4. **Technical Constraints** — limitations of the environment, tools, APIs
5. **Effort Estimation** — relative complexity of each component (low/medium/high)
6. **Validation Strategy** — how to verify each component works correctly

Think step-by-step. Be thorough. This analysis will feed into the structured plan.
Use the same language as the user's task description."""

# ---------------------------------------------------------------------------
# Phase 2: Structured Plan — JSON from analysis
# ---------------------------------------------------------------------------

PLAN_SYSTEM_PROMPT = """You are a planning assistant converting a deep analysis into a structured execution plan.

You will receive a task description AND a detailed analysis. Convert this into a precise JSON plan.

You MUST respond with valid JSON only, no markdown, no explanation. The JSON must have this exact structure:

{
  "title": "Plan title (concise, under 60 chars)",
  "summary": "2-3 sentence summary including key risks and approach",
  "sections": [
    {
      "id": "s1",
      "title": "Section title",
      "description": "What this section does and why",
      "steps": ["Step 1: concrete action", "Step 2: concrete action"],
      "dependencies": ["s0"],
      "risks": ["Risk description and mitigation"],
      "effort": "low|medium|high",
      "validation": "How to verify this section succeeded"
    }
  ]
}

Rules:
- Break the task into 3-10 logical sections based on the analysis
- Each section should be independently reviewable
- Steps should be concrete and actionable (include file paths, commands, API calls)
- "dependencies" lists section IDs that must complete first (empty array if none)
- "risks" lists specific risks for this section with mitigation strategies
- "effort" is one of: "low" (< 30 min), "medium" (30 min - 2 hr), "high" (> 2 hr)
- "validation" describes how to verify correctness (test command, visual check, etc.)
- Order sections respecting dependency graph
- Use the same language as the user's task description
"""

SECTION_REGEN_PROMPT = """You are revising ONE section of an execution plan based on user feedback.

Current plan title: {plan_title}
Current plan summary: {plan_summary}

All sections (for dependency context):
{all_sections_summary}

Section to revise:
- ID: {section_id}
- Title: {section_title}
- Description: {section_description}
- Steps: {section_steps}
- Dependencies: {section_dependencies}
- Risks: {section_risks}
- Effort: {section_effort}
- Validation: {section_validation}

User feedback: {feedback}

Respond with valid JSON only — the revised section object:
{{
  "id": "{section_id}",
  "title": "...",
  "description": "...",
  "steps": ["..."],
  "dependencies": ["..."],
  "risks": ["..."],
  "effort": "low|medium|high",
  "validation": "..."
}}
"""


def _extract_text(response: Dict[str, Any]) -> str:
    """Extract text content from LLM response."""
    content = response.get("content", [])
    for block in content:
        if isinstance(block, dict) and block.get("type") == "text":
            return block["text"]
        elif isinstance(block, str):
            return block
    return ""


def _clean_json(text: str) -> str:
    """Strip markdown fences and whitespace from JSON response."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()


async def _invoke_llm(model: str, system: str, messages: List[Dict], max_tokens: int = 8192, temperature: float = 0.3):
    """Invoke LLM via vendor router."""
    from .vendor_router import get_vendor_router
    router = get_vendor_router()
    request = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "system": system,
        "temperature": temperature,
    }
    model_id, bedrock_body = router.convert_request_to_bedrock(request, include_tools=False)
    return await router.invoke_model(model_id, bedrock_body)


async def generate_ultraplan(
    task_description: str,
    model: str = "claude-sonnet-4-6",
    max_tokens: int = 16384,
    context_messages: Optional[List[Dict[str, Any]]] = None,
) -> AsyncGenerator[Dict[str, Any], None]:
    """Generate an ultraplan via multi-phase analysis. Yields phase events."""

    # Build context from conversation history
    context_msgs: List[Dict] = []
    if context_messages:
        for msg in context_messages[-10:]:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if isinstance(content, str) and content.strip():
                context_msgs.append({"role": role, "content": content})

    # ── Phase 1: Deep Analysis ──
    yield {"phase": "analysis", "status": "start"}

    analysis_messages = context_msgs + [{
        "role": "user",
        "content": f"Perform deep analysis for this task:\n\n{task_description}",
    }]

    try:
        analysis_response = await _invoke_llm(
            model=model,
            system=ANALYSIS_SYSTEM_PROMPT,
            messages=analysis_messages,
            max_tokens=max_tokens,
            temperature=0.4,
        )
        analysis_text = _extract_text(analysis_response)
        if not analysis_text:
            raise ValueError("Empty analysis response")

        yield {"phase": "analysis", "status": "complete", "content": analysis_text}
    except Exception as e:
        logger.error(f"Analysis phase failed: {e}")
        yield {"phase": "analysis", "status": "error", "error": str(e)}
        raise

    # ── Phase 2: Structured Plan from Analysis ──
    yield {"phase": "planning", "status": "start"}

    plan_messages = [{
        "role": "user",
        "content": (
            f"Task description:\n{task_description}\n\n"
            f"--- Deep Analysis ---\n{analysis_text}\n\n"
            f"Convert the above analysis into a structured JSON execution plan."
        ),
    }]

    try:
        plan_response = await _invoke_llm(
            model=model,
            system=PLAN_SYSTEM_PROMPT,
            messages=plan_messages,
            max_tokens=max_tokens,
            temperature=0.2,
        )
        plan_text = _extract_text(plan_response)
        if not plan_text:
            raise ValueError("Empty plan response")

        plan_json = _clean_json(plan_text)
        plan_data = json.loads(plan_json)

        plan_id = f"plan-{uuid.uuid4().hex[:12]}"
        now = datetime.now().isoformat()

        sections = []
        for i, s in enumerate(plan_data.get("sections", [])):
            sections.append({
                "id": s.get("id", f"s{i+1}"),
                "title": s.get("title", f"Section {i+1}"),
                "description": s.get("description", ""),
                "steps": s.get("steps", []),
                "dependencies": s.get("dependencies", []),
                "risks": s.get("risks", []),
                "effort": s.get("effort", "medium"),
                "validation": s.get("validation", ""),
                "status": "pending",
                "feedback": None,
                "result": None,
            })

        plan = {
            "id": plan_id,
            "title": plan_data.get("title", "Untitled Plan"),
            "summary": plan_data.get("summary", ""),
            "analysis": analysis_text,
            "sections": sections,
            "status": "reviewing",
            "created_at": now,
            "updated_at": now,
        }

        yield {"phase": "planning", "status": "complete", "plan": plan}

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse plan JSON: {e}\nRaw: {plan_text[:500]}")
        yield {"phase": "planning", "status": "error", "error": f"Invalid JSON: {e}"}
        raise ValueError(f"Model returned invalid JSON: {e}")
    except Exception as e:
        logger.error(f"Planning phase failed: {e}")
        yield {"phase": "planning", "status": "error", "error": str(e)}
        raise


async def regenerate_section(
    plan: Dict[str, Any],
    section_id: str,
    feedback: str,
    model: str = "claude-sonnet-4-6",
    max_tokens: int = 4096,
) -> Dict[str, Any]:
    """Regenerate a single section based on user feedback."""

    section = None
    for s in plan.get("sections", []):
        if s["id"] == section_id:
            section = s
            break
    if not section:
        raise ValueError(f"Section {section_id} not found in plan")

    all_sections_summary = "\n".join(
        f"  - {s['id']}: {s['title']} (deps: {s.get('dependencies', [])})"
        for s in plan.get("sections", [])
    )

    prompt = SECTION_REGEN_PROMPT.format(
        plan_title=plan.get("title", ""),
        plan_summary=plan.get("summary", ""),
        all_sections_summary=all_sections_summary,
        section_id=section_id,
        section_title=section.get("title", ""),
        section_description=section.get("description", ""),
        section_steps=json.dumps(section.get("steps", []), ensure_ascii=False),
        section_dependencies=json.dumps(section.get("dependencies", []), ensure_ascii=False),
        section_risks=json.dumps(section.get("risks", []), ensure_ascii=False),
        section_effort=section.get("effort", "medium"),
        section_validation=section.get("validation", ""),
        feedback=feedback,
    )

    try:
        response = await _invoke_llm(
            model=model,
            system="Respond with valid JSON only.",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
        )

        text = _clean_json(_extract_text(response))
        updated = json.loads(text)
        updated["id"] = section_id
        updated.setdefault("dependencies", [])
        updated.setdefault("risks", [])
        updated.setdefault("effort", "medium")
        updated.setdefault("validation", "")
        updated["status"] = "pending"
        updated["feedback"] = None
        updated["result"] = None
        return updated

    except Exception as e:
        logger.error(f"Section regeneration failed: {e}")
        raise
