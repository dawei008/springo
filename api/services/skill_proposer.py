"""
Skill Proposer

Looks at a freshly-archived session and asks Haiku whether the interaction
contains a reusable pattern worth turning into a persistent skill. If yes,
writes a SKILL.md draft to `~/.springo/skills/_proposals/<slug>/` and
returns the proposal id so the frontend can surface it for user approval.

This is the write side of the self-evolution loop:
    session archive → proposal → user approves → skill lives in ~/.springo/skills/<slug>/

The read side (`skill_proposals_store`) lists, approves, or rejects drafts.
"""

import json
import logging
import os
import re
import shutil
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

PROPOSALS_DIR = Path(os.path.expanduser("~/.springo/skills/_proposals"))
REJECTIONS_FILE = PROPOSALS_DIR / ".rejections.json"

# Max proposals pending before we stop generating new ones (UX back-pressure).
MAX_PENDING = 20


_PROPOSAL_PROMPT = """You are a skill curator for a long-running AI assistant.

Below is a recently-archived conversation between the user and the assistant. Your job: decide whether this session surfaced a **reusable pattern** worth turning into a persistent Skill (a YAML-headed Markdown file the assistant will load in future sessions).

A good skill proposal meets ALL of these:
- The pattern would likely repeat — same kind of task, same kind of mistake, same kind of user preference — in future sessions
- The proposed guidance is NOT already captured in existing skills (if you recognize one of these names, skip: {existing_skills})
- The guidance is concrete and actionable (specific commands, patterns, or rules — not vague advice like "be helpful")

Reject cases (respond with exactly `NO_PROPOSAL`):
- One-off tasks (fixing a single typo, one-time data migration)
- Information already obvious from code or standard docs
- Patterns that belong in memory/feedback, not a skill (e.g. "user prefers X" — that's a memory, not a skill)
- Anything the user explicitly corrected or rejected

If you have a valid proposal, respond with **exactly** this format and NOTHING else:

```
TITLE: <short human-friendly name, 3-8 words>
SLUG: <lowercase-hyphenated, max 40 chars>
TRIGGER: <one sentence: when should this skill activate>
---
<full SKILL.md body starting with YAML frontmatter>
```

The SKILL.md body MUST start with:
```
---
name: <slug>
description: <one sentence description + concrete trigger phrases the user might say>
---

# <Title>

<instructions to the assistant, Markdown, code blocks welcome>
```

Session transcript:
{transcript}
"""


@dataclass
class SkillProposal:
    id: str                # proposal uuid
    slug: str              # target skill slug (also the dir name under _proposals/)
    title: str
    trigger: str           # one-line when-to-use
    skill_md: str          # full proposed SKILL.md body
    source_session_id: str
    created_at: str        # ISO
    status: str = "pending"  # pending | approved | rejected
    approved_skill_dir: Optional[str] = None


# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------

def _index_path() -> Path:
    return PROPOSALS_DIR / "index.json"


def _load_index() -> List[Dict[str, Any]]:
    p = _index_path()
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save_index(entries: List[Dict[str, Any]]) -> None:
    PROPOSALS_DIR.mkdir(parents=True, exist_ok=True)
    _index_path().write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_rejections() -> set:
    if not REJECTIONS_FILE.exists():
        return set()
    try:
        return set(json.loads(REJECTIONS_FILE.read_text(encoding="utf-8")))
    except Exception:
        return set()


def _save_rejections(slugs: set) -> None:
    PROPOSALS_DIR.mkdir(parents=True, exist_ok=True)
    REJECTIONS_FILE.write_text(json.dumps(sorted(slugs), ensure_ascii=False, indent=2), encoding="utf-8")


def _list_existing_skills() -> List[str]:
    skills_dir = Path(os.path.expanduser("~/.springo/skills"))
    if not skills_dir.exists():
        return []
    names = []
    for child in skills_dir.iterdir():
        if child.is_dir() and not child.name.startswith(("_", ".")) and (child / "SKILL.md").exists():
            names.append(child.name)
    return sorted(names)


# ---------------------------------------------------------------------------
# Haiku response parsing
# ---------------------------------------------------------------------------

_HEADER_RE = re.compile(
    r"^TITLE:\s*(?P<title>.+?)\n"
    r"SLUG:\s*(?P<slug>.+?)\n"
    r"TRIGGER:\s*(?P<trigger>.+?)\n"
    r"---\n"
    r"(?P<body>.*)$",
    re.DOTALL,
)


def _parse_proposal_response(text: str) -> Optional[Dict[str, str]]:
    text = text.strip()
    if not text or "NO_PROPOSAL" in text.upper():
        return None

    # Allow leading ``` wrapper
    if text.startswith("```"):
        text = re.sub(r"^```[a-z]*\n", "", text)
        text = re.sub(r"\n```$", "", text)

    m = _HEADER_RE.match(text)
    if not m:
        return None

    slug = m.group("slug").strip().lower()
    slug = re.sub(r"[^a-z0-9-]+", "-", slug).strip("-")[:40]
    if not slug:
        return None

    body = m.group("body").strip()
    # Proposal must have YAML frontmatter
    if not body.startswith("---"):
        return None

    return {
        "title": m.group("title").strip(),
        "slug": slug,
        "trigger": m.group("trigger").strip(),
        "skill_md": body,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def propose_skill_from_session(session_id: str, transcript: str) -> Optional[SkillProposal]:
    """
    Ask Haiku whether `transcript` warrants a new skill. If yes, write a draft
    under `~/.springo/skills/_proposals/<slug>/SKILL.md` and return the proposal.
    Returns None when nothing warrants a proposal.

    Safe to call fire-and-forget; exceptions are logged, not raised.
    """
    try:
        index = _load_index()
        pending = [e for e in index if e.get("status") == "pending"]
        if len(pending) >= MAX_PENDING:
            logger.info(f"[Proposer] Skipped: {len(pending)} pending proposals (limit {MAX_PENDING})")
            return None

        existing = _list_existing_skills()
        rejected = _load_rejections()

        prompt = _PROPOSAL_PROMPT.format(
            existing_skills=", ".join(existing) if existing else "(none)",
            transcript=transcript[:30000],  # safety cap
        )

        from .bedrock import get_bedrock_service
        from .model_registry import get_bedrock_id
        from ..config import get_settings

        bedrock = get_bedrock_service()
        settings = get_settings()
        model_name = settings.compact_model_id or "claude-haiku-4-5-20251001"
        # Force Anthropic format for Haiku
        if model_name.startswith(("us.", "deepseek.", "minimax.", "moonshotai.", "moonshot.", "qwen.", "zai.")):
            model_id = model_name
        else:
            model_id = get_bedrock_id(model_name)

        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 2048,
            "temperature": 0.2,
            "messages": [{"role": "user", "content": prompt}],
        }

        result = await bedrock.invoke_model(model_id=model_id, body=body, api_format="anthropic")

        text = ""
        if isinstance(result, dict):
            for block in result.get("content", []) or []:
                if isinstance(block, dict) and block.get("type") == "text":
                    text = block.get("text", "")
                    break

        parsed = _parse_proposal_response(text)
        if not parsed:
            logger.debug(f"[Proposer] No skill worth proposing from session {session_id}")
            return None

        slug = parsed["slug"]

        # Skip if slug is already an active skill or previously rejected
        if slug in existing:
            logger.info(f"[Proposer] Skipped: '{slug}' already exists in skills/")
            return None
        if slug in rejected:
            logger.info(f"[Proposer] Skipped: '{slug}' was previously rejected")
            return None
        # Skip if there is already a pending proposal for this slug
        if any(e.get("slug") == slug and e.get("status") == "pending" for e in index):
            logger.info(f"[Proposer] Skipped: proposal for '{slug}' already pending")
            return None

        # Write the draft
        proposal_id = f"prop-{int(time.time())}-{os.urandom(3).hex()}"
        draft_dir = PROPOSALS_DIR / slug
        draft_dir.mkdir(parents=True, exist_ok=True)
        (draft_dir / "SKILL.md").write_text(parsed["skill_md"], encoding="utf-8")

        proposal = SkillProposal(
            id=proposal_id,
            slug=slug,
            title=parsed["title"],
            trigger=parsed["trigger"],
            skill_md=parsed["skill_md"],
            source_session_id=session_id,
            created_at=datetime.utcnow().isoformat(timespec="seconds") + "Z",
        )
        index.append(asdict(proposal))
        _save_index(index)
        logger.info(f"[Proposer] New skill proposal: {slug} (id={proposal_id}) from session {session_id}")
        return proposal

    except Exception as e:
        logger.warning(f"[Proposer] Failed to propose skill from session {session_id}: {e}")
        return None


def list_proposals(status: Optional[str] = None) -> List[Dict[str, Any]]:
    """Return proposals, optionally filtered by status."""
    index = _load_index()
    if status:
        return [e for e in index if e.get("status") == status]
    return index


def get_proposal(proposal_id: str) -> Optional[Dict[str, Any]]:
    for e in _load_index():
        if e.get("id") == proposal_id:
            return e
    return None


def approve_proposal(proposal_id: str, edited_skill_md: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Move a proposal's draft into `~/.springo/skills/<slug>/`."""
    index = _load_index()
    for entry in index:
        if entry.get("id") != proposal_id:
            continue
        if entry.get("status") != "pending":
            return entry

        slug = entry["slug"]
        src = PROPOSALS_DIR / slug
        dst = Path(os.path.expanduser(f"~/.springo/skills/{slug}"))
        if dst.exists():
            logger.warning(f"[Proposer] Cannot approve '{slug}': destination already exists")
            return None

        dst.mkdir(parents=True, exist_ok=False)
        skill_md = edited_skill_md if edited_skill_md is not None else (src / "SKILL.md").read_text(encoding="utf-8")
        (dst / "SKILL.md").write_text(skill_md, encoding="utf-8")
        # Marker so the daily distiller knows this skill was auto-generated.
        # Only auto-generated skills are eligible for usage-based archive,
        # protecting plugin-installed and user-authored skills.
        (dst / ".auto_generated").write_text(
            f"approved_from_proposal={proposal_id}\napproved_at={datetime.utcnow().isoformat(timespec='seconds')}Z\n",
            encoding="utf-8",
        )
        entry["skill_md"] = skill_md
        entry["status"] = "approved"
        entry["approved_skill_dir"] = str(dst)
        _save_index(index)
        # Clean up the draft directory
        shutil.rmtree(src, ignore_errors=True)
        logger.info(f"[Proposer] Approved '{slug}' → {dst}")
        return entry
    return None


def reject_proposal(proposal_id: str) -> Optional[Dict[str, Any]]:
    """Mark a proposal rejected and remember the slug so we don't re-propose it."""
    index = _load_index()
    for entry in index:
        if entry.get("id") != proposal_id:
            continue
        if entry.get("status") != "pending":
            return entry
        slug = entry["slug"]
        entry["status"] = "rejected"
        _save_index(index)
        # Remember the rejection so future archives skip this slug
        rejections = _load_rejections()
        rejections.add(slug)
        _save_rejections(rejections)
        # Clean up draft dir
        shutil.rmtree(PROPOSALS_DIR / slug, ignore_errors=True)
        logger.info(f"[Proposer] Rejected '{slug}'")
        return entry
    return None
