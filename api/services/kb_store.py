"""
Local Knowledge Base store — ~/.springo/kb/

Three layers, two write zones:
- raw/   original sources (don't edit, only add)
- wiki/  AI-curated structured notes (edit freely)
- index.md / log.md / graph.json — derived from wiki/

Storage substrate is plain markdown. graph.json is a *view* regenerated
from wiki/ frontmatter; deleting it never loses data. No database.

Design notes are in ~/.springo/kb/CLAUDE.md (seeded on first ensure_kb()).
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .kb_templates import CLAUDE_MD, AGENTS_MD

logger = logging.getLogger(__name__)

KB_ROOT = Path.home() / ".springo" / "kb"
RAW_DIR = KB_ROOT / "raw"
WIKI_DIR = KB_ROOT / "wiki"
INDEX_FILE = KB_ROOT / "index.md"
LOG_FILE = KB_ROOT / "log.md"
GRAPH_FILE = KB_ROOT / "graph.json"
CLAUDE_FILE = KB_ROOT / "CLAUDE.md"
AGENTS_FILE = KB_ROOT / "AGENTS.md"

SIZE_50MB = 50 * 1024 * 1024
SIZE_1GB = 1024 * 1024 * 1024
RAW_BUDGET_BYTES = 5 * 1024 * 1024 * 1024  # 5 GB warn threshold


# Quick-aligned entity vocabulary. Frontmatter `node_type:` accepts any of
# these (case/space insensitive). Pages without a node_type fall back to
# "creative_work" so existing KB content keeps working.
NODE_TYPES: tuple = (
    "person", "organization", "place", "event",
    "product", "service", "project", "dataset",
    "creative_work", "defined_term", "instruction",
    "action", "channel", "observation", "decision",
    "occupation", "dashboard", "message", "visual",
)
DEFAULT_NODE_TYPE = "creative_work"


def normalize_node_type(value: Any) -> str:
    """Coerce a frontmatter ``node_type`` value into the canonical vocabulary.

    Accepts ``Person`` / ``defined-term`` / ``Defined Term`` / etc. Unknown
    values fall back to DEFAULT_NODE_TYPE so the graph never breaks on a typo.
    """
    if not value:
        return DEFAULT_NODE_TYPE
    s = str(value).strip().lower().replace(" ", "_").replace("-", "_")
    return s if s in NODE_TYPES else DEFAULT_NODE_TYPE


# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------

def ensure_kb() -> None:
    """Idempotently create directory tree + seed CLAUDE.md / AGENTS.md.

    Also seeds the bundled `kb-ingest` skill into ~/.springo/skills/ on
    first run so the AI knows how to add documents to the KB without the
    user manually copying anything.
    """
    for d in (KB_ROOT, RAW_DIR, WIKI_DIR):
        d.mkdir(parents=True, exist_ok=True)
    if not CLAUDE_FILE.exists():
        CLAUDE_FILE.write_text(CLAUDE_MD, encoding="utf-8")
    if not AGENTS_FILE.exists():
        AGENTS_FILE.write_text(AGENTS_MD, encoding="utf-8")
    if not INDEX_FILE.exists():
        INDEX_FILE.write_text(
            "# Knowledge Base Index\n\n"
            "_Auto-maintained. The AI updates this on every ingest._\n\n"
            "## Pages\n\n",
            encoding="utf-8",
        )
    if not LOG_FILE.exists():
        LOG_FILE.write_text("# KB Event Log\n\n_Append-only. Newest first._\n\n", encoding="utf-8")
    _seed_bundled_skills()


def _seed_bundled_skills() -> None:
    """Copy `api/services/seed_skills/*` into ~/.springo/skills/ if not
    already present. Idempotent — never overwrites a user-edited skill."""
    src_root = Path(__file__).parent / "seed_skills"
    if not src_root.exists():
        return
    skills_dir = Path.home() / ".springo" / "skills"
    skills_dir.mkdir(parents=True, exist_ok=True)
    for skill_dir in src_root.iterdir():
        if not skill_dir.is_dir():
            continue
        dst = skills_dir / skill_dir.name
        if dst.exists():
            continue
        try:
            shutil.copytree(skill_dir, dst)
            # Mark as bundled-but-eligible-for-reseed-on-update if missing.
            logger.info(f"[kb] seeded bundled skill → {dst}")
        except Exception as e:
            logger.warning(f"[kb] failed to seed skill {skill_dir.name}: {e}")


# ---------------------------------------------------------------------------
# Frontmatter parsing — minimal YAML
# ---------------------------------------------------------------------------

_FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)


def parse_frontmatter(content: str) -> Tuple[Dict[str, Any], str]:
    """Return (frontmatter dict, body). Frontmatter parser is intentionally
    forgiving — keys we care about are simple. For nested lists (sources)
    we fall back to a tolerant line-based parse.
    """
    m = _FM_RE.match(content)
    if not m:
        return {}, content.strip()

    fm_text, body = m.group(1), m.group(2).strip()
    out: Dict[str, Any] = {}

    # Try PyYAML if available — much safer for `sources:` lists.
    try:
        import yaml  # type: ignore
        try:
            parsed = yaml.safe_load(fm_text) or {}
            if isinstance(parsed, dict):
                return parsed, body
        except Exception as e:
            logger.debug(f"[kb] yaml frontmatter parse failed, falling back: {e}")
    except Exception:
        pass

    # Tolerant fallback: top-level `key: value` only. `sources:` is left as
    # a raw string blob so callers know the page exists, even if we can't
    # introspect the source list.
    current_key: Optional[str] = None
    block_lines: List[str] = []
    for line in fm_text.split("\n"):
        if not line.strip():
            continue
        if line.startswith(("  ", "\t", "-")):
            block_lines.append(line)
            continue
        if current_key:
            out[current_key] = "\n".join(block_lines).strip() if block_lines else out.get(current_key)
            block_lines = []
        if ":" in line:
            k, _, v = line.partition(":")
            current_key = k.strip()
            v = v.strip().strip('"').strip("'")
            if v:
                out[current_key] = v
                current_key = None
            else:
                out[current_key] = ""
    if current_key and block_lines:
        out[current_key] = "\n".join(block_lines).strip()

    # Tags handling: turn "[a, b]" or "a, b" into list.
    if "tags" in out and isinstance(out["tags"], str):
        s = out["tags"].strip().lstrip("[").rstrip("]")
        out["tags"] = [t.strip() for t in s.split(",") if t.strip()]
    return out, body


# ---------------------------------------------------------------------------
# Slug + filename helpers
# ---------------------------------------------------------------------------

def slugify(s: str, max_len: int = 60) -> str:
    s = s.strip().lower()
    s = re.sub(r"[\s_/\\]+", "-", s)
    s = re.sub(r"[^a-z0-9一-鿿-]+", "", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return (s or "untitled")[:max_len]


def _wiki_path(slug: str) -> Path:
    if not re.fullmatch(r"[a-z0-9一-鿿-]{1,80}", slug):
        raise ValueError(f"Unsafe slug: {slug!r}")
    return WIKI_DIR / f"{slug}.md"


# ---------------------------------------------------------------------------
# Wiki CRUD
# ---------------------------------------------------------------------------

def list_pages() -> List[Dict[str, Any]]:
    ensure_kb()
    out: List[Dict[str, Any]] = []
    for f in sorted(WIKI_DIR.glob("*.md")):
        try:
            fm, _ = parse_frontmatter(f.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"[kb] failed to parse {f.name}: {e}")
            fm = {}
        stat = f.stat()
        out.append({
            "slug": fm.get("slug") or f.stem,
            "title": fm.get("title") or f.stem,
            "tags": fm.get("tags") or [],
            "last_updated": fm.get("last_updated"),
            "size_bytes": stat.st_size,
            "modified": int(stat.st_mtime * 1000),
        })
    return out


def read_page(slug: str) -> Dict[str, Any]:
    ensure_kb()
    p = _wiki_path(slug)
    if not p.exists():
        raise FileNotFoundError(f"Page not found: {slug}")
    text = p.read_text(encoding="utf-8")
    fm, body = parse_frontmatter(text)
    return {
        "slug": slug,
        "title": fm.get("title") or slug,
        "frontmatter": fm,
        "body": body,
        "raw": text,
    }


def write_page(slug: str, content: str) -> Dict[str, Any]:
    """Write a wiki page. Caller is responsible for content shape; we just
    enforce that frontmatter exists and add `last_updated` if missing."""
    ensure_kb()
    p = _wiki_path(slug)
    if not content.startswith("---"):
        # Wrap with a minimal frontmatter so even hand-written notes
        # pass schema lint.
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        content = (
            f"---\ntitle: {slug}\nslug: {slug}\ntags: []\nsources: []\n"
            f"created_at: {today}\nlast_updated: {today}\n---\n\n" + content
        )
    p.write_text(content, encoding="utf-8")
    _regenerate_graph()
    return {"slug": slug, "size_bytes": p.stat().st_size}


def delete_page(slug: str) -> bool:
    p = _wiki_path(slug)
    if not p.exists():
        return False
    p.unlink()
    _regenerate_graph()
    return True


# ---------------------------------------------------------------------------
# Ingest — size-tier policy
# ---------------------------------------------------------------------------

def _sha256_of(path: Path, chunk: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for buf in iter(lambda: f.read(chunk), b""):
            h.update(buf)
    return h.hexdigest()


def _raw_dir_total_bytes() -> int:
    if not RAW_DIR.exists():
        return 0
    return sum(f.stat().st_size for f in RAW_DIR.rglob("*") if f.is_file())


def plan_ingest(source_path: str) -> Dict[str, Any]:
    """Inspect a candidate source and return the recommended tier + flags.
    Doesn't move bytes — preview only. Caller decides whether to commit.
    """
    ensure_kb()
    src = Path(source_path).expanduser().resolve()
    if not src.exists() or not src.is_file():
        raise FileNotFoundError(f"Source file not found: {source_path}")
    size = src.stat().st_size
    if size < SIZE_50MB:
        tier = "full"
        ask = False
        reason = "< 50 MB"
    elif size < SIZE_1GB:
        tier = "full"
        ask = True
        reason = "50 MB – 1 GB: confirm before copying"
    else:
        tier = "digest-only"
        ask = True
        reason = "≥ 1 GB: original will not be copied"
    raw_total = _raw_dir_total_bytes()
    over_budget = (raw_total + size) > RAW_BUDGET_BYTES
    return {
        "source_path": str(src),
        "size_bytes": size,
        "tier": tier,
        "needs_confirmation": ask or over_budget,
        "reason": reason,
        "raw_total_after": raw_total + (size if tier == "full" else 0),
        "raw_budget_bytes": RAW_BUDGET_BYTES,
        "over_budget": over_budget,
    }


def commit_ingest_full(source_path: str, slug_hint: Optional[str] = None) -> Dict[str, Any]:
    """Copy the source file into raw/. Use ONLY for tier=full. Returns a
    dict with the new raw path + sha256 for the AI to write into the
    wiki page's frontmatter."""
    ensure_kb()
    plan = plan_ingest(source_path)
    if plan["tier"] != "full":
        raise ValueError(
            f"Refusing full-copy: tier is {plan['tier']!r} ({plan['reason']!r}). "
            "Use commit_ingest_digest for digest-only sources."
        )
    src = Path(plan["source_path"])
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    base = slugify(slug_hint or src.stem)
    dst = RAW_DIR / f"{today}-{base}{src.suffix}"
    # Don't clobber: tag a counter if needed.
    n = 1
    while dst.exists():
        n += 1
        dst = RAW_DIR / f"{today}-{base}-{n}{src.suffix}"
    shutil.copy2(src, dst)
    sha = _sha256_of(dst)
    return {
        "raw_path": str(dst.relative_to(KB_ROOT)),
        "size_bytes": dst.stat().st_size,
        "sha256": sha,
        "tier": "full",
    }


def commit_ingest_digest(
    *,
    title: str,
    transcript: str,
    original_path: Optional[str] = None,
    original_url: Optional[str] = None,
    original_size_bytes: Optional[int] = None,
    extra_meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Write a digest-only entry. Original file is NOT copied. Use for
    audio/video/anything ≥ 1 GB. The AI extracts a transcript / text dump
    upstream and passes it here."""
    ensure_kb()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    base = slugify(title)
    dst = RAW_DIR / f"{today}-{base}.transcript.md"
    n = 1
    while dst.exists():
        n += 1
        dst = RAW_DIR / f"{today}-{base}-{n}.transcript.md"
    dst.write_text(transcript, encoding="utf-8")
    meta = {
        "title": title,
        "tier": "digest-only",
        "stored_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "original_path": original_path,
        "original_url": original_url,
        "original_size_bytes": original_size_bytes,
    }
    if extra_meta:
        meta.update(extra_meta)
    meta_path = dst.with_suffix(".meta.json")
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "raw_path": str(dst.relative_to(KB_ROOT)),
        "meta_path": str(meta_path.relative_to(KB_ROOT)),
        "tier": "digest-only",
    }


def commit_ingest_external(
    *, title: str, external_path: str, sha256: Optional[str] = None,
) -> Dict[str, Any]:
    """User explicitly designates an external location. We only write a stub."""
    ensure_kb()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    base = slugify(title)
    dst = RAW_DIR / f"{today}-{base}.stub.md"
    n = 1
    while dst.exists():
        n += 1
        dst = RAW_DIR / f"{today}-{base}-{n}.stub.md"
    ext = Path(external_path).expanduser()
    size = ext.stat().st_size if ext.exists() else None
    if not sha256 and ext.exists() and (size or 0) < 200 * 1024 * 1024:
        # Skip sha256 for huge external files; user can verify by hand.
        sha256 = _sha256_of(ext)
    body = (
        f"# External source: {title}\n\n"
        f"- external_path: `{external_path}`\n"
        f"- size_bytes: {size}\n"
        f"- sha256: `{sha256 or '(not computed)'}`\n"
        f"- registered_at: {datetime.now(timezone.utc).isoformat(timespec='seconds')}\n"
    )
    dst.write_text(body, encoding="utf-8")
    return {
        "raw_path": str(dst.relative_to(KB_ROOT)),
        "external_path": external_path,
        "size_bytes": size,
        "sha256": sha256,
        "tier": "external",
    }


def ingest_text(*, title: str, content: str, source_url: Optional[str] = None) -> Dict[str, Any]:
    """Convenience for pasted content / extracted webpage text — always
    `full` because content is always a small markdown blob."""
    ensure_kb()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    base = slugify(title)
    dst = RAW_DIR / f"{today}-{base}.md"
    n = 1
    while dst.exists():
        n += 1
        dst = RAW_DIR / f"{today}-{base}-{n}.md"
    head = f"<!-- source_url: {source_url} -->\n" if source_url else ""
    dst.write_text(head + content, encoding="utf-8")
    return {
        "raw_path": str(dst.relative_to(KB_ROOT)),
        "size_bytes": dst.stat().st_size,
        "tier": "full",
    }


# ---------------------------------------------------------------------------
# graph.json — derived view
# ---------------------------------------------------------------------------

_LINK_RE = re.compile(r"\[\[([^\]\n]+?)\]\]")


def _regenerate_graph() -> Dict[str, Any]:
    """Walk wiki/, build node + edge list. Always overwrites graph.json."""
    ensure_kb()
    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, str]] = []
    seen_slugs: set = set()
    page_records: List[Tuple[str, str, Dict[str, Any]]] = []

    now = datetime.now(timezone.utc)

    for f in sorted(WIKI_DIR.glob("*.md")):
        try:
            text = f.read_text(encoding="utf-8")
        except Exception:
            continue
        fm, body = parse_frontmatter(text)
        slug = fm.get("slug") or f.stem
        seen_slugs.add(slug)
        page_records.append((slug, body, fm))

    for slug, body, fm in page_records:
        # Count claims = bullets under "## Key claims" up to next "## "
        claim_count = 0
        in_claims = False
        for line in body.split("\n"):
            stripped = line.strip()
            if stripped.startswith("##"):
                in_claims = stripped.lower().startswith("## key claim")
                continue
            if in_claims and stripped.startswith(("- ", "* ", "+ ")):
                claim_count += 1

        sources = fm.get("sources") if isinstance(fm.get("sources"), list) else []
        last_raw = fm.get("last_updated")
        # PyYAML auto-parses YYYY-MM-DD as date / datetime objects. Normalize
        # everything to an ISO string for transport + downstream math.
        last_str: str = ""
        if last_raw is not None:
            if hasattr(last_raw, "isoformat"):
                last_str = last_raw.isoformat()
            else:
                last_str = str(last_raw)
        try:
            last_dt = datetime.fromisoformat(last_str)
            if last_dt.tzinfo is None:
                last_dt = last_dt.replace(tzinfo=timezone.utc)
            stale_days = (now - last_dt).days
            stale = stale_days > 180
        except Exception:
            stale = False

        nodes.append({
            "id": slug,
            "title": fm.get("title") or slug,
            "tags": fm.get("tags") or [],
            "node_type": normalize_node_type(fm.get("node_type")),
            "source": "kb",
            "claim_count": claim_count,
            "source_count": len(sources) if isinstance(sources, list) else 0,
            "last_updated": last_str or None,
            "stale": stale,
            "orphan": False,  # filled below
        })

        # Typed relations: optional ``relations:`` frontmatter list lets a page
        # declare semantic edges, e.g.
        #   relations:
        #     - { to: "anthropic", kind: "works_at" }
        #     - { to: "claude", kind: "created" }
        # We collect those slugs first so they win over the fallback see-also.
        explicit_targets: set = set()
        rels = fm.get("relations")
        if isinstance(rels, list):
            for r in rels:
                if not isinstance(r, dict):
                    continue
                target = (r.get("to") or "").strip()
                kind = (r.get("kind") or "see-also").strip() or "see-also"
                if target and target != slug:
                    edges.append({"from": slug, "to": target, "kind": kind})
                    explicit_targets.add(target)

        # see-also fallback: parse `[[slug]]` from "## See also" section,
        # then whole body. Skip targets already covered by typed relations.
        see_also_section = ""
        in_see = False
        for line in body.split("\n"):
            if line.strip().lower().startswith("## see also"):
                in_see = True
                continue
            if in_see and line.startswith("##"):
                break
            if in_see:
                see_also_section += line + "\n"
        link_targets = set(_LINK_RE.findall(see_also_section or body))
        for target in link_targets:
            target_slug = target.strip().split("|")[0].strip()
            if target_slug and target_slug != slug and target_slug not in explicit_targets:
                edges.append({"from": slug, "to": target_slug, "kind": "see-also"})

    # Multi-source aggregation: pull memory files + chat sessions in as
    # additional nodes. They share the schema so they merge cleanly. Failures
    # never bubble up — the wiki KB stays usable even if memory dirs are
    # weird.
    try:
        from .kb_sources import list_memory_nodes, list_chat_nodes
        mem_nodes, mem_edges = list_memory_nodes(now=now)
        chat_nodes, chat_edges = list_chat_nodes(now=now)
        nodes.extend(mem_nodes)
        nodes.extend(chat_nodes)
        edges.extend(mem_edges)
        edges.extend(chat_edges)
    except Exception as e:
        logger.warning(f"[kb] multi-source aggregation failed: {e}")

    # Mark orphans (no inbound edges) — applies to KB wiki nodes only;
    # memory/chat nodes are stand-alone islands by construction.
    inbound = {e["to"] for e in edges}
    for node in nodes:
        if node.get("source") != "kb":
            continue
        if node["id"] not in inbound and node["id"] in seen_slugs:
            node["orphan"] = True

    raw_index: List[Dict[str, Any]] = []
    if RAW_DIR.exists():
        for f in sorted(RAW_DIR.iterdir()):
            if f.is_file():
                raw_index.append({
                    "path": str(f.relative_to(KB_ROOT)),
                    "size_bytes": f.stat().st_size,
                })

    graph = {
        "generated_at": now.isoformat(timespec="seconds"),
        "nodes": nodes,
        "edges": edges,
        "raw_index": raw_index,
        "stats": {
            "page_count": len(nodes),
            "edge_count": len(edges),
            "orphan_count": sum(1 for n in nodes if n["orphan"]),
            "stale_count": sum(1 for n in nodes if n["stale"]),
            "raw_count": len(raw_index),
            "raw_total_bytes": sum(r["size_bytes"] for r in raw_index),
        },
    }
    # default=str so date / datetime objects (from yaml.safe_load) serialize.
    GRAPH_FILE.write_text(
        json.dumps(graph, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    return graph


def get_graph() -> Dict[str, Any]:
    ensure_kb()
    if not GRAPH_FILE.exists():
        return _regenerate_graph()
    try:
        return json.loads(GRAPH_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return _regenerate_graph()


# ---------------------------------------------------------------------------
# Log + lint
# ---------------------------------------------------------------------------

def append_log(entry: str) -> None:
    ensure_kb()
    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    block = f"## [{timestamp}] {entry.strip()}\n\n"
    existing = LOG_FILE.read_text(encoding="utf-8") if LOG_FILE.exists() else ""
    LOG_FILE.write_text(block + existing, encoding="utf-8")


def lint() -> Dict[str, Any]:
    """Run a lint pass; pure analysis, never mutates wiki/ or raw/."""
    ensure_kb()
    pages = list_pages()
    graph = _regenerate_graph()

    findings: Dict[str, List[Any]] = {
        "orphans": [n["id"] for n in graph["nodes"] if n["orphan"]],
        "stale": [n["id"] for n in graph["nodes"] if n["stale"]],
        "missing_tags": [n["id"] for n in graph["nodes"] if not n["tags"]],
        "no_sources": [n["id"] for n in graph["nodes"] if n["source_count"] == 0],
        "dead_sources": [],
        "schema_drift": [],
    }

    for p in pages:
        try:
            page = read_page(p["slug"])
        except Exception:
            findings["schema_drift"].append({"slug": p["slug"], "issue": "unreadable"})
            continue
        fm = page["frontmatter"]
        sources = fm.get("sources")
        if not isinstance(sources, list):
            continue
        for src in sources:
            if not isinstance(src, dict):
                continue
            if src.get("storage") == "full":
                fpath = src.get("file")
                if fpath and not (KB_ROOT / fpath).exists():
                    findings["dead_sources"].append({"slug": p["slug"], "missing_file": fpath})

    summary = {k: len(v) for k, v in findings.items()}
    append_log(
        f"lint — orphans:{summary['orphans']} stale:{summary['stale']} "
        f"missing_tags:{summary['missing_tags']} no_sources:{summary['no_sources']} "
        f"dead_sources:{summary['dead_sources']} schema_drift:{summary['schema_drift']}"
    )
    return {"findings": findings, "summary": summary, "stats": graph["stats"]}


# ---------------------------------------------------------------------------
# Public surface
# ---------------------------------------------------------------------------

def stats() -> Dict[str, Any]:
    ensure_kb()
    graph = get_graph()
    return {
        **graph["stats"],
        "raw_budget_bytes": RAW_BUDGET_BYTES,
        "kb_root": str(KB_ROOT),
    }
