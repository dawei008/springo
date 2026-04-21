"""
Skill Evaluator for Springo

Mines session history to evaluate skill effectiveness using
keyword proxy scoring and LLM-as-judge.
"""

import json
import os
import re
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field, asdict
from datetime import datetime

logger = logging.getLogger(__name__)

SKILLS_DIR = Path(os.path.expanduser("~/.springo/skills"))
SESSIONS_DIR = Path(os.path.expanduser("~/.springo/sessions"))


@dataclass
class SkillUsageRecord:
    session_id: str
    skill_name: str
    timestamp: str
    user_request: str
    assistant_response: str
    tool_calls: List[str]
    outcome: str  # "completed", "error", "abandoned"


@dataclass
class EvalScore:
    correctness: float
    procedure_following: float
    conciseness: float
    notes: str = ""


@dataclass
class SkillEvalResult:
    skill_name: str
    evaluated_at: str
    usage_count: int
    sampled_count: int
    avg_correctness: float
    avg_procedure_following: float
    avg_conciseness: float
    overall_score: float
    keyword_proxy_score: float
    individual_scores: List[Dict[str, Any]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Session mining
# ---------------------------------------------------------------------------

def _parse_session_messages(session_path: Path) -> List[Dict[str, Any]]:
    """Parse messages from a session JSONL file."""
    messages = []
    try:
        with open(session_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    if obj.get("type") == "metadata":
                        continue
                    if "role" in obj:
                        messages.append(obj)
                except json.JSONDecodeError:
                    continue
    except Exception as e:
        logger.debug(f"Failed to parse session {session_path}: {e}")
    return messages


def _extract_text(content: Any) -> str:
    """Extract text from message content (string or content blocks)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                if block.get("type") == "text":
                    parts.append(block.get("text", ""))
        return "\n".join(parts)
    return ""


def _extract_tool_uses(content: Any) -> List[Dict[str, Any]]:
    """Extract tool_use blocks from message content."""
    if not isinstance(content, list):
        return []
    return [b for b in content if isinstance(b, dict) and b.get("type") == "tool_use"]


def find_skill_usages(
    skill_name: str,
    max_sessions: int = 50,
) -> List[SkillUsageRecord]:
    """Scan session files for conversations where a skill was used."""
    usages: List[SkillUsageRecord] = []

    if not SESSIONS_DIR.exists():
        return usages

    # Sort session dirs by modification time (newest first)
    session_dirs = sorted(
        [d for d in SESSIONS_DIR.iterdir() if d.is_dir()],
        key=lambda d: d.stat().st_mtime,
        reverse=True,
    )[:max_sessions]

    for session_dir in session_dirs:
        # Find the JSONL file
        jsonl_files = list(session_dir.glob("*.jsonl"))
        if not jsonl_files:
            continue
        jsonl_file = jsonl_files[0]

        messages = _parse_session_messages(jsonl_file)
        if not messages:
            continue

        session_id = session_dir.name

        # Scan for use_skill tool calls matching this skill
        for i, msg in enumerate(messages):
            if msg.get("role") != "assistant":
                continue

            tool_uses = _extract_tool_uses(msg.get("content", []))
            for tu in tool_uses:
                if tu.get("name") != "use_skill":
                    continue
                tool_input = tu.get("input", {})
                if tool_input.get("skill_name") != skill_name:
                    continue

                # Found a skill usage — extract context
                user_request = ""
                for j in range(i - 1, -1, -1):
                    if messages[j].get("role") == "user":
                        user_request = _extract_text(messages[j].get("content", ""))
                        break

                # Collect assistant response after skill activation
                assistant_parts = []
                subsequent_tools = []
                for j in range(i + 1, min(i + 10, len(messages))):
                    m = messages[j]
                    if m.get("role") == "assistant":
                        text = _extract_text(m.get("content", ""))
                        if text:
                            assistant_parts.append(text)
                        for t in _extract_tool_uses(m.get("content", [])):
                            subsequent_tools.append(t.get("name", ""))
                    elif m.get("role") == "user":
                        break

                # Determine outcome
                full_response = "\n".join(assistant_parts)
                if any(w in full_response.lower() for w in ["error", "failed", "exception"]):
                    outcome = "error"
                elif not assistant_parts:
                    outcome = "abandoned"
                else:
                    outcome = "completed"

                ts = msg.get("timestamp", datetime.now().isoformat())
                if isinstance(ts, (int, float)):
                    ts = datetime.fromtimestamp(ts / 1000 if ts > 1e12 else ts).isoformat()

                usages.append(SkillUsageRecord(
                    session_id=session_id,
                    skill_name=skill_name,
                    timestamp=str(ts),
                    user_request=user_request[:2000],
                    assistant_response=full_response[:3000],
                    tool_calls=subsequent_tools[:20],
                    outcome=outcome,
                ))

    return usages


# ---------------------------------------------------------------------------
# Keyword proxy (fast scoring without LLM)
# ---------------------------------------------------------------------------

_POSITIVE_SIGNALS = [
    "done", "complete", "success", "created", "saved", "finished",
    "thank", "perfect", "great", "works",
]
_NEGATIVE_SIGNALS = [
    "error", "failed", "wrong", "broken", "doesn't work", "bug",
    "not what", "undo", "revert",
]


def keyword_proxy_score(usage: SkillUsageRecord) -> float:
    """Fast heuristic scoring without LLM call.

    Returns 0.0-1.0 composite score.
    """
    score = 0.0
    response_lower = usage.assistant_response.lower()
    request_lower = usage.user_request.lower()

    # Outcome bonus
    if usage.outcome == "completed":
        score += 0.3
    elif usage.outcome == "error":
        score -= 0.1

    # Tool usage indicates skill was actionable
    if usage.tool_calls:
        score += 0.2

    # Positive signals in response
    positive_count = sum(1 for w in _POSITIVE_SIGNALS if w in response_lower)
    score += min(0.2, positive_count * 0.05)

    # Negative signals
    negative_count = sum(1 for w in _NEGATIVE_SIGNALS if w in response_lower)
    score -= min(0.2, negative_count * 0.05)

    # Response length — neither too short nor too long
    response_len = len(usage.assistant_response)
    if 100 < response_len < 5000:
        score += 0.15
    elif response_len < 20:
        score -= 0.1

    # Has substantive user request
    if len(usage.user_request) > 10:
        score += 0.05

    return max(0.0, min(1.0, score))


# ---------------------------------------------------------------------------
# LLM-as-judge
# ---------------------------------------------------------------------------

_JUDGE_PROMPT = """You are evaluating an AI agent's use of a skill.

Skill instructions:
<instructions>
{instructions}
</instructions>

User request: {user_request}

Agent response (truncated):
{assistant_response}

Tools called after skill activation: {tool_calls}
Outcome: {outcome}

Rate the following on a scale of 0.0 to 1.0:
1. correctness: Did the agent produce the correct result for the user's request?
2. procedure_following: Did the agent follow the skill's step-by-step instructions?
3. conciseness: Was the response appropriately concise without unnecessary verbosity?

Respond ONLY with JSON (no markdown, no explanation):
{{"correctness": 0.X, "procedure_following": 0.X, "conciseness": 0.X, "notes": "brief note"}}"""


async def llm_judge_score(
    usage: SkillUsageRecord,
    skill_instructions: str,
    vendor_router=None,
    judge_model: str = "claude-haiku-4-5-20251001",
) -> EvalScore:
    """Score a skill usage via LLM-as-judge."""
    if vendor_router is None:
        return EvalScore(correctness=0.0, procedure_following=0.0, conciseness=0.0,
                         notes="No vendor router available")

    prompt = _JUDGE_PROMPT.format(
        instructions=skill_instructions[:3000],
        user_request=usage.user_request[:1000],
        assistant_response=usage.assistant_response[:2000],
        tool_calls=", ".join(usage.tool_calls[:10]) or "none",
        outcome=usage.outcome,
    )

    try:
        response = await vendor_router.invoke_model(
            model=judge_model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,
            temperature=0.0,
            stream=False,
        )

        # Extract text from response
        text = ""
        if isinstance(response, dict):
            content = response.get("content", [])
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        text = block.get("text", "")
                        break
            elif isinstance(content, str):
                text = content
        elif isinstance(response, str):
            text = response

        # Parse JSON from response
        json_match = re.search(r'\{[^}]+\}', text)
        if json_match:
            data = json.loads(json_match.group())
            return EvalScore(
                correctness=float(data.get("correctness", 0)),
                procedure_following=float(data.get("procedure_following", 0)),
                conciseness=float(data.get("conciseness", 0)),
                notes=str(data.get("notes", "")),
            )
    except Exception as e:
        logger.warning(f"LLM judge failed: {e}")

    return EvalScore(correctness=0.0, procedure_following=0.0, conciseness=0.0,
                     notes="Judge call failed")


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

async def evaluate_skill(
    skill_name: str,
    max_samples: int = 10,
    use_llm: bool = True,
    vendor_router=None,
    judge_model: str = "claude-haiku-4-5-20251001",
) -> SkillEvalResult:
    """Full evaluation pipeline for a skill.

    1. Mine sessions for usages
    2. Sample up to max_samples
    3. Run keyword proxy on all
    4. Optionally run LLM judge on samples
    5. Aggregate scores
    6. Save to EVAL.json
    """
    # Load skill instructions for judge context
    skill_instructions = ""
    try:
        from api.services.skill_loader import get_skill_loader
        loader = get_skill_loader()
        skill = loader.get_skill(skill_name)
        if skill:
            skill_instructions = skill.instructions
    except Exception:
        pass

    # 1. Mine sessions
    all_usages = find_skill_usages(skill_name, max_sessions=100)
    usage_count = len(all_usages)

    if usage_count == 0:
        result = SkillEvalResult(
            skill_name=skill_name,
            evaluated_at=datetime.now().isoformat(),
            usage_count=0,
            sampled_count=0,
            avg_correctness=0.0,
            avg_procedure_following=0.0,
            avg_conciseness=0.0,
            overall_score=0.0,
            keyword_proxy_score=0.0,
        )
        save_eval_result(result)
        return result

    # 2. Sample
    samples = all_usages[:max_samples]

    # 3. Keyword proxy on all
    proxy_scores = [keyword_proxy_score(u) for u in all_usages]
    avg_proxy = sum(proxy_scores) / len(proxy_scores) if proxy_scores else 0.0

    # 4. LLM judge on samples
    individual_scores = []
    if use_llm and vendor_router and skill_instructions:
        for usage in samples:
            score = await llm_judge_score(
                usage, skill_instructions, vendor_router, judge_model
            )
            individual_scores.append({
                "session_id": usage.session_id,
                "correctness": score.correctness,
                "procedure_following": score.procedure_following,
                "conciseness": score.conciseness,
                "notes": score.notes,
                "proxy_score": keyword_proxy_score(usage),
            })
    else:
        for usage in samples:
            proxy = keyword_proxy_score(usage)
            individual_scores.append({
                "session_id": usage.session_id,
                "correctness": proxy,
                "procedure_following": proxy,
                "conciseness": proxy,
                "notes": "keyword proxy only",
                "proxy_score": proxy,
            })

    # 5. Aggregate
    if individual_scores:
        avg_correctness = sum(s["correctness"] for s in individual_scores) / len(individual_scores)
        avg_procedure = sum(s["procedure_following"] for s in individual_scores) / len(individual_scores)
        avg_conciseness = sum(s["conciseness"] for s in individual_scores) / len(individual_scores)
        overall = 0.5 * avg_correctness + 0.3 * avg_procedure + 0.2 * avg_conciseness
    else:
        avg_correctness = avg_procedure = avg_conciseness = overall = 0.0

    result = SkillEvalResult(
        skill_name=skill_name,
        evaluated_at=datetime.now().isoformat(),
        usage_count=usage_count,
        sampled_count=len(samples),
        avg_correctness=round(avg_correctness, 3),
        avg_procedure_following=round(avg_procedure, 3),
        avg_conciseness=round(avg_conciseness, 3),
        overall_score=round(overall, 3),
        keyword_proxy_score=round(avg_proxy, 3),
        individual_scores=individual_scores,
    )

    # 6. Save
    save_eval_result(result)
    return result


def load_eval_result(skill_name: str) -> Optional[SkillEvalResult]:
    """Load cached EVAL.json for a skill."""
    eval_path = SKILLS_DIR / skill_name / "EVAL.json"
    if not eval_path.exists():
        return None
    try:
        data = json.loads(eval_path.read_text(encoding='utf-8'))
        return SkillEvalResult(**data)
    except Exception:
        return None


def save_eval_result(result: SkillEvalResult) -> Path:
    """Save evaluation results to EVAL.json."""
    eval_path = SKILLS_DIR / result.skill_name / "EVAL.json"
    eval_path.parent.mkdir(parents=True, exist_ok=True)
    eval_path.write_text(json.dumps(asdict(result), indent=2, ensure_ascii=False), encoding='utf-8')
    logger.info(f"Saved eval for '{result.skill_name}': score={result.overall_score}, usages={result.usage_count}")
    return eval_path
