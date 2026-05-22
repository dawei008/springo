"""
Knowledge Base tools — let the AI ingest sources, write pages, search,
and read pages directly from chat without HTTP gymnastics.

These wrap api/services/kb_store.py. Failures return a JSON-serializable
error string (not exceptions) so the chat loop can handle them gracefully.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _store():
    """Lazy import — kb_store boots a directory on first call, no need to
    pay that cost at module import."""
    from api.services import kb_store
    return kb_store


def _err(msg: str) -> Dict[str, Any]:
    return {"ok": False, "error": msg}


def _ok(payload: Dict[str, Any]) -> Dict[str, Any]:
    out = {"ok": True}
    out.update(payload)
    return out


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

def kb_list(scope: str = "all") -> Dict[str, Any]:
    """List wiki pages. scope='all' returns titles + slugs + tags +
    counts; scope='orphans' / 'stale' filter the same list."""
    try:
        store = _store()
        pages = store.list_pages()
        graph = store.get_graph()
        # Index orphan/stale flags by slug.
        flags = {n["id"]: n for n in graph.get("nodes", [])}
        out: List[Dict[str, Any]] = []
        for p in pages:
            node = flags.get(p["slug"], {})
            entry = {
                "slug": p["slug"],
                "title": p.get("title"),
                "tags": p.get("tags") or [],
                "last_updated": p.get("last_updated"),
                "claim_count": node.get("claim_count", 0),
                "source_count": node.get("source_count", 0),
                "orphan": bool(node.get("orphan")),
                "stale": bool(node.get("stale")),
            }
            if scope == "orphans" and not entry["orphan"]:
                continue
            if scope == "stale" and not entry["stale"]:
                continue
            out.append(entry)
        return _ok({"pages": out, "total": len(out), "stats": graph.get("stats")})
    except Exception as e:
        logger.warning(f"[kb_list] {e}")
        return _err(str(e))


def kb_search(query: str, max_results: int = 10) -> Dict[str, Any]:
    """Plain-text grep across wiki/*.md (titles + bodies). Returns matched
    pages with the line that hit and surrounding context.

    Per CLAUDE.md, we don't chunk or embed — we grep, then the AI reads
    full pages of interest with kb_read_page."""
    try:
        store = _store()
        pages = store.list_pages()
        if not query.strip():
            return _ok({"results": [], "query": query})
        q = query.lower()
        matches: List[Dict[str, Any]] = []
        for p in pages:
            try:
                page = store.read_page(p["slug"])
            except Exception:
                continue
            text = page["raw"]
            if q not in text.lower() and q not in (p.get("title") or "").lower():
                continue
            # Find first matching line for snippet.
            snippet = ""
            for line in text.split("\n"):
                if q in line.lower():
                    snippet = line.strip()[:200]
                    break
            matches.append({
                "slug": p["slug"],
                "title": p.get("title"),
                "tags": p.get("tags") or [],
                "snippet": snippet,
            })
            if len(matches) >= max_results:
                break
        return _ok({"results": matches, "query": query, "total": len(matches)})
    except Exception as e:
        logger.warning(f"[kb_search] {e}")
        return _err(str(e))


def kb_read_page(slug: str) -> Dict[str, Any]:
    """Read one wiki page in full. Returns frontmatter + body."""
    try:
        page = _store().read_page(slug)
        return _ok({
            "slug": page["slug"],
            "title": page["title"],
            "frontmatter": page["frontmatter"],
            "body": page["body"],
        })
    except FileNotFoundError as e:
        return _err(str(e))
    except Exception as e:
        logger.warning(f"[kb_read_page] {e}")
        return _err(str(e))


# ---------------------------------------------------------------------------
# Authoring
# ---------------------------------------------------------------------------

def kb_write_page(slug: str, content: str) -> Dict[str, Any]:
    """Write or replace a wiki page. The content MUST start with the
    schema's frontmatter block (see CLAUDE.md). If you're just adding
    claims to an existing page, prefer reading the page first, editing
    the body, and writing the whole thing back."""
    try:
        result = _store().write_page(slug, content)
        return _ok(result)
    except ValueError as e:
        return _err(str(e))
    except Exception as e:
        logger.warning(f"[kb_write_page] {e}")
        return _err(str(e))


def kb_ingest_text(
    title: str,
    content: str,
    source_url: Optional[str] = None,
) -> Dict[str, Any]:
    """Ingest small inline text (a snippet, a webpage extraction, a
    pasted email) into raw/. Always tier=full because content is a
    pre-extracted text blob — never huge. Returns the raw_path so you
    can reference it from a wiki page's `sources:` list."""
    try:
        result = _store().ingest_text(title=title, content=content, source_url=source_url)
        return _ok(result)
    except Exception as e:
        logger.warning(f"[kb_ingest_text] {e}")
        return _err(str(e))


def kb_ingest_file(source_path: str, slug_hint: Optional[str] = None) -> Dict[str, Any]:
    """Ingest a file from disk into raw/. The store decides the tier
    by size:
    - < 50 MB → full (file copied)
    - 50 MB – 1 GB → planned, requires user confirmation (see plan output)
    - > 1 GB → REFUSED here; use kb_ingest_external or extract a
      transcript and call kb_ingest_text instead.
    """
    try:
        store = _store()
        plan = store.plan_ingest(source_path)
        if plan.get("needs_confirmation"):
            # Don't auto-commit large-ish files. Let the AI surface the
            # plan to the user and await an explicit decision.
            return _ok({
                "committed": False,
                "needs_user_confirmation": True,
                "plan": plan,
                "next_step": "ask user to confirm, then call kb_ingest_file again with confirm=true",
            })
        if plan.get("tier") != "full":
            return _err(
                f"File tier is {plan.get('tier')!r} — use kb_ingest_external for ≥ 1 GB files "
                "or extract a transcript via kb_ingest_text."
            )
        result = store.commit_ingest_full(source_path, slug_hint)
        return _ok({"committed": True, **result})
    except FileNotFoundError as e:
        return _err(str(e))
    except ValueError as e:
        return _err(str(e))
    except Exception as e:
        logger.warning(f"[kb_ingest_file] {e}")
        return _err(str(e))


def kb_ingest_pdf(source_path: str, slug_hint: Optional[str] = None) -> Dict[str, Any]:
    """Ingest a PDF: copy original (if size permits) AND return extracted
    text so the AI can immediately distill it into wiki pages without a
    second tool round-trip."""
    try:
        store = _store()
        # Step 1: copy/plan.
        ingest_result = kb_ingest_file(source_path, slug_hint)
        if not ingest_result.get("ok"):
            return ingest_result
        # If it needs confirmation, surface the plan and bail.
        if ingest_result.get("needs_user_confirmation"):
            return ingest_result

        # Step 2: extract text via pypdf if available.
        text = ""
        page_count = 0
        try:
            from pypdf import PdfReader  # type: ignore
            reader = PdfReader(source_path)
            page_count = len(reader.pages)
            chunks: List[str] = []
            for i, page in enumerate(reader.pages):
                try:
                    chunks.append(f"--- p{i+1} ---\n" + (page.extract_text() or ""))
                except Exception as e:
                    chunks.append(f"--- p{i+1} (extraction failed: {e}) ---")
            text = "\n\n".join(chunks)
        except ImportError:
            return _err(
                "pypdf not installed. Install with `pip install pypdf` or "
                "extract the PDF text manually and pass via kb_ingest_text."
            )
        except Exception as e:
            logger.warning(f"[kb_ingest_pdf] extract failed: {e}")
            return _err(f"PDF extraction failed: {e}")

        # Cap returned text to keep tool result small; AI can re-read raw if needed.
        truncated = len(text) > 50000
        excerpt = text[:50000]
        return _ok({
            **ingest_result,
            "page_count": page_count,
            "text_excerpt": excerpt,
            "text_truncated": truncated,
            "text_length": len(text),
            "next_step": (
                "Now write 1+ wiki pages using kb_write_page. Each page must "
                "follow the schema in ~/.springo/kb/CLAUDE.md (frontmatter + "
                "summary + key claims with source pointers + see-also). Use "
                f"the raw_path returned ({ingest_result.get('raw_path')}) as "
                "the source pointer in your claims."
            ),
        })
    except Exception as e:
        logger.warning(f"[kb_ingest_pdf] {e}")
        return _err(str(e))


def kb_lint() -> Dict[str, Any]:
    """Run the lint pass: orphans, dead sources, schema drift, stale
    pages. Read-only — never deletes or rewrites. Use to find what
    needs cleanup, then apply fixes via kb_write_page."""
    try:
        return _ok(_store().lint())
    except Exception as e:
        logger.warning(f"[kb_lint] {e}")
        return _err(str(e))


def kb_stats() -> Dict[str, Any]:
    """Top-level KB metrics: page count, edge count, orphan count, raw
    storage usage. Cheap call."""
    try:
        return _ok(_store().stats())
    except Exception as e:
        return _err(str(e))
