"""
Multi-source aggregator for the knowledge graph.

Adds nodes from beyond the curated KB wiki:

  - ``memory``  — every Markdown file under known memory roots
                  (``~/.claude/projects/*/memory/`` plus
                  ``~/.springo/workspace/memory/``)
  - ``chat``    — entities mined from chat session transcripts; see
                  ``kb_chat_entities`` for the heuristic extractor.

Each emitter returns a list of node dicts that match the same shape
``kb_store.regenerate_graph`` produces, so the graph endpoint can simply
concatenate them.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

logger = logging.getLogger(__name__)

# Memory roots scanned on every regenerate. Both directories are optional —
# missing roots just contribute zero nodes.
_MEMORY_ROOTS: tuple = (
    Path.home() / ".springo" / "workspace" / "memory",
    Path.home() / ".claude" / "projects",  # walk recursively for memory/*.md
)

# A memory file path looks like "<title or YYYY-MM-DD>.md". Strip the
# extension and lowercase for the slug. Prefix with "mem-" so it can never
# collide with KB wiki slugs.
def _memory_slug(path: Path) -> str:
    base = path.stem.strip().lower()
    base = re.sub(r"[^a-z0-9_-]+", "-", base).strip("-") or "memory"
    return f"mem-{base}"


def _extract_title(path: Path, body: str) -> str:
    """Prefer the first ``# heading`` line, fall back to filename stem."""
    for line in body.splitlines():
        s = line.strip()
        if s.startswith("# ") and len(s) > 2:
            return s[2:].strip()
        if s and not s.startswith("#"):
            break
    return path.stem


def list_memory_nodes(now: datetime | None = None) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Walk every memory root and return (nodes, edges).

    Edges link successive daily logs (``mem-2026-05-25 -> mem-2026-05-24``)
    so the graph reflects temporal order without needing inline links.
    """
    now = now or datetime.now(timezone.utc)
    nodes: List[Dict[str, Any]] = []
    seen: set = set()
    daily_chronological: List[str] = []  # for inter-day edges

    for root in _MEMORY_ROOTS:
        if not root.exists():
            continue
        # Recurse only when the path itself is named "memory" or has a
        # "memory" subdir; otherwise we'd pull in unrelated docs.
        candidates: List[Path] = []
        if root.name == "memory":
            candidates = sorted(root.glob("*.md"))
        else:
            for d in root.glob("*/memory"):
                candidates.extend(sorted(d.glob("*.md")))

        for f in candidates:
            try:
                text = f.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            slug = _memory_slug(f)
            if slug in seen:
                continue
            seen.add(slug)

            title = _extract_title(f, text)
            mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)
            stale = (now - mtime).days > 60

            # Detect daily-log style filenames (YYYY-MM-DD.md) so we can
            # chain them temporally below.
            is_daily = bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", f.stem))

            nodes.append({
                "id": slug,
                "title": title,
                "tags": ["memory"] + (["daily"] if is_daily else []),
                "node_type": "observation",
                "source": "memory",
                "claim_count": len([l for l in text.splitlines() if l.strip().startswith(("- ", "* "))]),
                "source_count": 1,
                "last_updated": mtime.date().isoformat(),
                "stale": stale,
                "orphan": False,
            })
            if is_daily:
                daily_chronological.append(slug)

    # Chain daily logs newest → previous so the graph shows a thin timeline.
    daily_chronological.sort(reverse=True)
    edges: List[Dict[str, Any]] = []
    for i in range(len(daily_chronological) - 1):
        edges.append({
            "from": daily_chronological[i],
            "to": daily_chronological[i + 1],
            "kind": "follows",
        })

    return nodes, edges


# Pattern matches `[[slug]]` wikilinks (Quick / Obsidian style) — these are
# the most reliable entity signal in chat content.
_WIKILINK_RE = re.compile(r"\[\[([^\]\|\n]{2,80})(?:\|[^\]]*)?\]\]")
# Match capitalized multi-word product / project / org names that recur.
# Demands at least two consecutive Capitalized tokens — single capitalized
# words ("Users", "Downloads") would otherwise dominate the noise floor.
_PROPER_NOUN_RE = re.compile(r"\b[A-Z][a-zA-Z0-9+.-]{1,20}(?:\s+[A-Z][a-zA-Z0-9+.-]{1,20}){1,3}\b")
# Stoplist: common false-positive multi-cap phrases.
_PROPER_NOUN_STOP: set = {
    "I", "OK", "TODO", "FIXME", "GET", "POST", "PUT", "DELETE", "PATCH",
    "AM", "PM", "PDT", "PST", "UTC",
    # Generic single-word nouns that bypass the bigram rule via punctuation.
    "Users", "Downloads", "Chrome", "HTML", "JSON", "CSS", "JavaScript",
    "TypeScript", "Python", "Bash", "Git", "GitHub", "API", "URL", "ID",
    "PDF", "PNG", "JPG", "SVG", "PR", "Hi", "Hello", "Yes", "No",
}
# Min mention count across the session before we accept a proper noun.
_MIN_MENTIONS = 3
# Cap globally extracted entities so the graph doesn't explode.
_MAX_GLOBAL_ENTITIES = 250


def _classify_entity(display: str) -> str:
    """Heuristic node_type for an extracted entity.

    Matches Quick's vocabulary so colors split out instead of every entity
    being the same orange ``defined_term``.
    """
    s = display.strip()
    lower = s.lower()
    # URLs / channel-like
    if "://" in s or s.startswith("@") or s.startswith("#"):
        return "channel"
    # Date-ish
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s) or re.fullmatch(r"Q[1-4]\s+\d{4}", s):
        return "event"
    # Trailing "API"/"SDK"/"Service" → service
    if re.search(r"\b(API|SDK|Service|Server|Endpoint|Bridge)\b", s):
        return "service"
    # All caps acronym (3-6 chars) usually a product / defined term
    if re.fullmatch(r"[A-Z]{3,6}", s):
        return "defined_term"
    # Product-y tail words
    if re.search(r"\b(App|Tool|Studio|Editor|Console|Dashboard|Console|UI)\b", s):
        return "product"
    if re.search(r"\bDashboard\b", s):
        return "dashboard"
    # We do NOT try to classify "FirstName LastName" as person — too many
    # false positives ("Bad Design", "Tool Use", etc). Without a name
    # dictionary the heuristic is worse than the default.
    # Trailing "Inc"/"Corp"/"Ltd"/"AG"/"GmbH" or contains "Team"/"Group"
    if re.search(r"\b(Inc|Corp|Ltd|AG|GmbH|Team|Group|Co\.)\b", s):
        return "organization"
    # "X.Y" version-like → product
    if re.search(r"\d+\.\d+", s):
        return "product"
    # Project-y: contains "project", "initiative", "migration"
    if re.search(r"(?i)\b(project|initiative|migration|refactor)\b", s):
        return "project"
    # Decision-y
    if re.search(r"(?i)\b(decision|choose|adopt)\b", s):
        return "decision"
    # Long single-token CamelCase: likely a product/codebase
    if " " not in s and re.fullmatch(r"[A-Z][a-zA-Z]+", s) and len(s) > 6:
        return "product"
    return "defined_term"


def _slugify_entity(name: str) -> str:
    s = name.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "entity"


def _read_session_text(jsonl_path: Path) -> str:
    """Concatenate all message text into one blob for cheap regex scans."""
    out: List[str] = []
    try:
        import json as _json
        with jsonl_path.open("r", encoding="utf-8", errors="replace") as fp:
            for line in fp:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = _json.loads(line)
                except Exception:
                    continue
                content = obj.get("content")
                if isinstance(content, str):
                    out.append(content)
                elif isinstance(content, list):
                    for b in content:
                        if isinstance(b, dict) and b.get("type") == "text":
                            out.append(b.get("text") or "")
    except Exception:
        pass
    return "\n".join(out)


def list_chat_nodes(now: datetime | None = None) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Each chat session becomes a node, plus extracted entity nodes linked
    via ``mentions`` edges to the session(s) that mentioned them.

    Heuristics:
      * ``[[wikilinks]]`` → high-confidence entity (always extracted).
      * Repeating capitalized multi-word phrases (≥3 mentions in session) →
        probable entity.

    Extracted entity slugs are deduped across sessions; many sessions may
    point at the same entity so the graph naturally clusters.
    """
    now = now or datetime.now(timezone.utc)
    sessions_root = Path.home() / ".springo" / "sessions"
    if not sessions_root.exists():
        return [], []

    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []
    entity_acc: Dict[str, Dict[str, Any]] = {}  # slug → node accumulator

    for d in sorted(sessions_root.iterdir()):
        if not d.is_dir():
            continue
        jsonls = list(d.glob("*.jsonl"))
        if not jsonls:
            continue
        f = jsonls[0]
        try:
            mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)
        except Exception:
            continue

        title = d.name
        try:
            with f.open("r", encoding="utf-8", errors="replace") as fp:
                first = fp.readline()
            import json as _json
            meta = _json.loads(first) if first else {}
            if isinstance(meta, dict):
                title = meta.get("title") or meta.get("name") or title
        except Exception:
            pass

        chat_slug = f"chat-{d.name}"
        try:
            line_count = sum(1 for _ in f.open("r", encoding="utf-8", errors="replace"))
        except Exception:
            line_count = 0

        nodes.append({
            "id": chat_slug,
            "title": title,
            "tags": ["chat"],
            "node_type": "message",
            "source": "chat",
            "claim_count": max(0, line_count - 1),
            "source_count": 1,
            "last_updated": mtime.date().isoformat(),
            "stale": (now - mtime).days > 90,
            "orphan": False,
        })

        # Mine the session body for entities. Skip very large sessions to
        # keep the graph rebuild snappy.
        if line_count > 5000:
            continue
        body = _read_session_text(f)
        if not body:
            continue

        mentioned: Dict[str, Tuple[str, str]] = {}  # slug → (display, source_tag)

        for m in _WIKILINK_RE.findall(body):
            display = m.strip()
            slug = _slugify_entity(display)
            if slug:
                mentioned[slug] = (display, "wikilink")

        # Proper-noun pass: count, filter, accept top hits.
        counts: Dict[str, Tuple[str, int]] = {}
        for m in _PROPER_NOUN_RE.findall(body):
            phrase = m.strip()
            if phrase in _PROPER_NOUN_STOP:
                continue
            if len(phrase) < 4:
                continue
            slug = _slugify_entity(phrase)
            cur = counts.get(slug)
            if cur:
                counts[slug] = (cur[0], cur[1] + 1)
            else:
                counts[slug] = (phrase, 1)
        for slug, (display, n) in counts.items():
            if slug in mentioned:
                continue
            if n < _MIN_MENTIONS:
                continue
            mentioned[slug] = (display, "noun")

        # Track per-session entity slugs so we can emit co-mention edges
        # afterward (so the graph isn't a star around each session).
        session_entity_slugs: List[str] = []
        for slug, (display, _src) in mentioned.items():
            acc = entity_acc.get(slug)
            if not acc:
                entity_acc[slug] = {
                    "id": f"ent-{slug}",
                    "title": display,
                    "tags": ["entity"],
                    "node_type": _classify_entity(display),
                    "source": "chat",
                    "claim_count": 1,
                    "source_count": 1,
                    "last_updated": mtime.date().isoformat(),
                    "stale": False,
                    "orphan": False,
                }
            else:
                acc["claim_count"] = acc.get("claim_count", 1) + 1
                if mtime.date().isoformat() > (acc.get("last_updated") or ""):
                    acc["last_updated"] = mtime.date().isoformat()
            edges.append({
                "from": chat_slug,
                "to": f"ent-{slug}",
                "kind": "mentions",
            })
            session_entity_slugs.append(slug)

        # Co-mention edges: every pair of entities mentioned in the same
        # session gets a single undirected edge. We dedupe by sorted pair so
        # multiple sessions mentioning the same pair count as one edge.
        seen_pairs: set = set()
        for i in range(len(session_entity_slugs)):
            for j in range(i + 1, len(session_entity_slugs)):
                a = session_entity_slugs[i]
                b = session_entity_slugs[j]
                if a == b:
                    continue
                pair = (min(a, b), max(a, b))
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)
                edges.append({
                    "from": f"ent-{pair[0]}",
                    "to": f"ent-{pair[1]}",
                    "kind": "co-mentioned",
                })

    # Cap the entity set to keep the graph readable. Keep the most-mentioned.
    if len(entity_acc) > _MAX_GLOBAL_ENTITIES:
        ranked = sorted(entity_acc.items(), key=lambda kv: -kv[1].get("claim_count", 0))
        kept_slugs = {slug for slug, _ in ranked[:_MAX_GLOBAL_ENTITIES]}
        entity_acc = {k: v for k, v in entity_acc.items() if k in kept_slugs}
        # Drop edges referring to dropped entities.
        keep_node_ids = {f"ent-{s}" for s in kept_slugs} | {n["id"] for n in nodes}
        edges = [e for e in edges if e["from"] in keep_node_ids and e["to"] in keep_node_ids]

    nodes.extend(entity_acc.values())
    return nodes, edges
