"""
Springo Plan Generation Service
计划生成服务 - 通过 LLM 生成结构化执行计划
"""
import json
import uuid
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)

PLAN_SYSTEM_PROMPT = """You are a planning assistant. Given a task description, generate a structured execution plan.

You MUST respond with valid JSON only, no markdown, no explanation. The JSON must have this exact structure:

{
  "title": "Plan title (concise, under 60 chars)",
  "summary": "1-2 sentence summary of what this plan accomplishes",
  "sections": [
    {
      "id": "s1",
      "title": "Section title",
      "description": "What this section does and why",
      "steps": ["Step 1 description", "Step 2 description"]
    }
  ]
}

Rules:
- Break the task into 3-8 logical sections
- Each section should be independently reviewable
- Steps should be concrete and actionable
- Order sections by dependency (earlier sections first)
- Use the same language as the user's task description
"""

SECTION_REGEN_PROMPT = """You are revising ONE section of an execution plan based on user feedback.

Current plan title: {plan_title}
Current plan summary: {plan_summary}

Section to revise:
- ID: {section_id}
- Title: {section_title}
- Description: {section_description}
- Steps: {section_steps}

User feedback: {feedback}

Respond with valid JSON only — the revised section object:
{{
  "id": "{section_id}",
  "title": "...",
  "description": "...",
  "steps": ["..."]
}}
"""


async def generate_plan(
    task_description: str,
    model: str = "claude-sonnet-4-6",
    max_tokens: int = 8192,
    context_messages: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Generate a structured plan from a task description."""
    from .bedrock import get_bedrock_service

    svc = get_bedrock_service()

    messages = []
    if context_messages:
        for msg in context_messages[-5:]:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if isinstance(content, str) and content.strip():
                messages.append({"role": role, "content": content})

    messages.append({
        "role": "user",
        "content": f"Generate a structured execution plan for this task:\n\n{task_description}"
    })

    try:
        # Build Anthropic-format request, then convert to Bedrock format
        request = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "system": PLAN_SYSTEM_PROMPT,
            "temperature": 0.3,
        }
        model_id, bedrock_body = svc.convert_request_to_bedrock(request, include_tools=False)
        response = await svc.invoke_model(model_id, bedrock_body)

        # Extract text from response
        text = ""
        content = response.get("content", [])
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                text = block["text"]
                break
            elif isinstance(block, str):
                text = block
                break

        if not text:
            raise ValueError("Empty response from model")

        # Clean JSON (strip markdown fences if present)
        text = text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

        plan_data = json.loads(text)

        plan_id = f"plan-{uuid.uuid4().hex[:12]}"
        now = datetime.now().isoformat()

        # Normalize sections
        sections = []
        for i, s in enumerate(plan_data.get("sections", [])):
            sections.append({
                "id": s.get("id", f"s{i+1}"),
                "title": s.get("title", f"Section {i+1}"),
                "description": s.get("description", ""),
                "steps": s.get("steps", []),
                "status": "pending",
                "feedback": None,
                "result": None,
            })

        return {
            "id": plan_id,
            "title": plan_data.get("title", "Untitled Plan"),
            "summary": plan_data.get("summary", ""),
            "sections": sections,
            "status": "reviewing",
            "created_at": now,
            "updated_at": now,
        }

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse plan JSON: {e}\nRaw text: {text[:500]}")
        raise ValueError(f"Model returned invalid JSON: {e}")
    except Exception as e:
        logger.error(f"Plan generation failed: {e}")
        raise


async def regenerate_section(
    plan: Dict[str, Any],
    section_id: str,
    feedback: str,
    model: str = "claude-sonnet-4-6",
    max_tokens: int = 4096,
) -> Dict[str, Any]:
    """Regenerate a single section based on user feedback."""
    from .bedrock import get_bedrock_service

    svc = get_bedrock_service()

    # Find the section
    section = None
    for s in plan.get("sections", []):
        if s["id"] == section_id:
            section = s
            break

    if not section:
        raise ValueError(f"Section {section_id} not found in plan")

    prompt = SECTION_REGEN_PROMPT.format(
        plan_title=plan.get("title", ""),
        plan_summary=plan.get("summary", ""),
        section_id=section_id,
        section_title=section.get("title", ""),
        section_description=section.get("description", ""),
        section_steps=json.dumps(section.get("steps", []), ensure_ascii=False),
        feedback=feedback,
    )

    try:
        request = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "system": "Respond with valid JSON only.",
            "temperature": 0.3,
        }
        model_id, bedrock_body = svc.convert_request_to_bedrock(request, include_tools=False)
        response = await svc.invoke_model(model_id, bedrock_body)

        text = ""
        content = response.get("content", [])
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                text = block["text"]
                break

        text = text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

        updated = json.loads(text)
        updated["id"] = section_id
        updated["status"] = "pending"
        updated["feedback"] = None
        updated["result"] = None

        return updated

    except Exception as e:
        logger.error(f"Section regeneration failed: {e}")
        raise
