"""
Springo UltraPlan Generation Service
深度计划服务 - 多阶段分析（含工具探索）→ 结构化执行计划

Phase 1 (Analysis) runs an agentic tool loop so the model can explore the
codebase, read files, grep for patterns, etc. before producing its analysis.
For non-code tasks the model simply reasons without calling any tools.

Phase 2 (Planning) converts the analysis into structured JSON — no tools needed.
"""
import json
import uuid
import logging
import asyncio
from typing import Optional, List, Dict, Any, AsyncGenerator
from datetime import datetime

logger = logging.getLogger(__name__)

READONLY_TOOLS = frozenset({
    "read_file", "read_files", "list_directory", "search_files",
    "glob", "grep", "get_file_info", "git",
    "lsp_go_to_definition", "lsp_find_references",
})

MAX_ANALYSIS_ITERATIONS = 15

# ---------------------------------------------------------------------------
# Phase 1: Deep Analysis — agentic exploration + reasoning
# ---------------------------------------------------------------------------

ANALYSIS_SYSTEM_PROMPT = """You are a senior technical architect performing deep analysis before creating an execution plan.

You have access to read-only tools (read_file, grep, glob, list_directory, etc.).
If the task involves code or files, USE the tools to explore the codebase first — read key files, search for patterns, understand the current state. Do NOT guess about code structure.
If the task is non-technical or doesn't require file exploration, just reason directly.

After exploration, produce a thorough analysis covering:

1. **Current State** — what exists now (based on what you read/found)
2. **Requirements Decomposition** — break the task into fundamental components
3. **Dependency Graph** — which components must come before others and why
4. **Risk Assessment** — what could go wrong, edge cases, failure modes
5. **Technical Constraints** — limitations of the environment, tools, APIs
6. **Effort Estimation** — relative complexity of each component (low/medium/high)
7. **Validation Strategy** — how to verify each component works correctly

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
    """Invoke LLM via vendor router (no tools)."""
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


async def _invoke_llm_with_tools(
    model: str,
    system: str,
    messages: List[Dict],
    tools: List[Dict],
    max_tokens: int = 8192,
    temperature: float = 0.3,
):
    """Invoke LLM via vendor router with tool definitions."""
    from .vendor_router import get_vendor_router
    router = get_vendor_router()
    request = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "system": system,
        "temperature": temperature,
    }
    model_id, bedrock_body = router.convert_request_to_bedrock(
        request,
        include_tools=True,
        tools=tools,
    )
    return await router.invoke_model(model_id, bedrock_body)


def _get_readonly_tools(all_tools: List) -> List[Dict]:
    """Filter tool definitions to read-only exploration tools."""
    result = []
    for t in all_tools:
        td = t.model_dump() if hasattr(t, "model_dump") else t
        if td.get("name") in READONLY_TOOLS:
            result.append(td)
    return result


async def _run_analysis_loop(
    model: str,
    messages: List[Dict],
    tools: List[Dict],
    max_tokens: int,
    session_id: Optional[str] = None,
) -> AsyncGenerator[Dict[str, Any], None]:
    """Run Phase 1 agentic loop: LLM calls tools to explore, then produces analysis.

    Yields events:
      {"type": "tool_call", "name": ..., "input": ...}
      {"type": "tool_result", "name": ..., "content": ..., "is_error": ...}
      {"type": "analysis_complete", "content": ...}
    """
    from .tool_manager import get_tool_manager
    tool_manager = await get_tool_manager()

    for iteration in range(MAX_ANALYSIS_ITERATIONS):
        if tools:
            response = await _invoke_llm_with_tools(
                model=model,
                system=ANALYSIS_SYSTEM_PROMPT,
                messages=messages,
                tools=tools,
                max_tokens=max_tokens,
                temperature=0.4,
            )
        else:
            response = await _invoke_llm(
                model=model,
                system=ANALYSIS_SYSTEM_PROMPT,
                messages=messages,
                max_tokens=max_tokens,
                temperature=0.4,
            )

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

        if not tool_uses or stop_reason != "tool_use":
            analysis_text = "".join(text_parts)
            yield {"type": "analysis_complete", "content": analysis_text}
            return

        # Append assistant message with all content blocks
        messages.append({"role": "assistant", "content": content_blocks})

        # Execute tools and collect results
        tool_results = []
        for tool in tool_uses:
            tool_name = tool.get("name", "")
            tool_input = tool.get("input", {})
            tool_id = tool.get("id", "")

            yield {"type": "tool_call", "name": tool_name, "input": tool_input}

            try:
                result = await asyncio.wait_for(
                    tool_manager.execute_tool(tool_name, tool_input, session_id=session_id),
                    timeout=30,
                )
                result_content = result.get("content", "") if isinstance(result, dict) else str(result)
                is_error = result.get("is_error", False) if isinstance(result, dict) else False
            except asyncio.TimeoutError:
                result_content = f"Tool {tool_name} timed out after 30s"
                is_error = True
            except Exception as e:
                result_content = f"Tool {tool_name} failed: {e}"
                is_error = True

            # Truncate large results to keep context manageable
            if len(str(result_content)) > 8000:
                result_content = str(result_content)[:8000] + "\n... (truncated)"

            yield {"type": "tool_result", "name": tool_name, "content": str(result_content)[:500], "is_error": is_error}

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tool_id,
                "content": str(result_content),
                "is_error": is_error,
            })

        messages.append({"role": "user", "content": tool_results})

    # Exhausted iterations — ask for final analysis without tools
    messages.append({"role": "user", "content": "You've done enough exploration. Now produce your final analysis based on everything you've learned."})
    response = await _invoke_llm(
        model=model,
        system=ANALYSIS_SYSTEM_PROMPT,
        messages=messages,
        max_tokens=max_tokens,
        temperature=0.4,
    )
    yield {"type": "analysis_complete", "content": _extract_text(response)}


async def generate_ultraplan(
    task_description: str,
    model: str = "claude-sonnet-4-6",
    max_tokens: int = 16384,
    context_messages: Optional[List[Dict[str, Any]]] = None,
    session_id: Optional[str] = None,
) -> AsyncGenerator[Dict[str, Any], None]:
    """Generate an ultraplan via multi-phase analysis. Yields phase events.

    Phase 1: Agentic exploration + deep analysis (with read-only tools)
    Phase 2: Structured JSON plan from analysis (no tools)
    """

    # Build context from conversation history
    context_msgs: List[Dict] = []
    if context_messages:
        for msg in context_messages[-10:]:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if isinstance(content, str) and content.strip():
                context_msgs.append({"role": role, "content": content})

    # Load read-only tools
    readonly_tools: List[Dict] = []
    try:
        from .tool_manager import get_tool_manager
        tool_manager = await get_tool_manager()
        all_tools = tool_manager.get_tool_definitions()
        readonly_tools = _get_readonly_tools(all_tools)
        logger.info(f"UltraPlan: loaded {len(readonly_tools)} read-only tools for analysis")
    except Exception as e:
        logger.warning(f"UltraPlan: could not load tools, analysis will be tool-free: {e}")

    # ── Phase 1: Agentic Analysis ──
    yield {"phase": "analysis", "status": "start"}

    analysis_messages = context_msgs + [{
        "role": "user",
        "content": f"Perform deep analysis for this task:\n\n{task_description}",
    }]

    try:
        analysis_text = ""
        tool_calls_made = 0
        async for event in _run_analysis_loop(
            model=model,
            messages=analysis_messages,
            tools=readonly_tools,
            max_tokens=max_tokens,
            session_id=session_id,
        ):
            if event["type"] == "tool_call":
                tool_calls_made += 1
                yield {
                    "phase": "analysis",
                    "status": "tool_call",
                    "tool_name": event["name"],
                    "tool_input": event.get("input", {}),
                    "tool_count": tool_calls_made,
                }
            elif event["type"] == "tool_result":
                yield {
                    "phase": "analysis",
                    "status": "tool_result",
                    "tool_name": event["name"],
                    "content": event.get("content", ""),
                    "is_error": event.get("is_error", False),
                }
            elif event["type"] == "analysis_complete":
                analysis_text = event["content"]

        if not analysis_text:
            raise ValueError("Empty analysis response")

        logger.info(f"UltraPlan: analysis complete ({tool_calls_made} tool calls, {len(analysis_text)} chars)")
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
