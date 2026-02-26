"""
Memory Tools — memory_search & memory_get
Three-tier memory retrieval:
  - recent (≤ retention_days): grep memory/*.md files directly
  - longterm (> retention_days): AgentCore Memory retrieve API
  - auto: search recent first, then longterm if needed
"""

import os
import re
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


def _get_memory_file_manager():
    """Lazy import to avoid circular dependencies."""
    try:
        from api.services.memory_files import get_memory_file_manager
        return get_memory_file_manager()
    except Exception:
        return None


def _search_recent_memory(query: str, max_results: int = 10, days: int = None) -> List[Dict[str, Any]]:
    """Search memory/*.md files using grep for recent memory.

    Uses simple text matching — no vector index needed since files are limited.
    """
    mgr = _get_memory_file_manager()
    if mgr is None:
        return []

    if days is None:
        days = mgr.retention_days

    # Collect files within date range
    cutoff = datetime.now() - timedelta(days=days)
    cutoff_str = cutoff.strftime("%Y-%m-%d")
    target_files: List[str] = []

    # Always include MEMORY.md
    if os.path.isfile(mgr.memory_md_path):
        target_files.append(mgr.memory_md_path)

    # Include memory/*.md within date range
    if os.path.isdir(mgr.memory_dir):
        for name in sorted(os.listdir(mgr.memory_dir), reverse=True):
            if not name.endswith(".md"):
                continue
            date_part = name[:10]
            if len(date_part) == 10 and date_part >= cutoff_str:
                target_files.append(os.path.join(mgr.memory_dir, name))

    if not target_files:
        return []

    # Search each file for query terms
    results: List[Dict[str, Any]] = []
    query_lower = query.lower()
    # Split query into terms for matching
    terms = [t.strip() for t in query_lower.split() if len(t.strip()) >= 2]
    if not terms:
        terms = [query_lower]

    for fpath in target_files:
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception:
            continue

        content_lower = content.lower()
        # Score: count how many query terms appear in the file
        matched_terms = sum(1 for t in terms if t in content_lower)
        if matched_terms == 0:
            continue

        score = matched_terms / len(terms)

        # Extract best matching snippet (context around first match)
        lines = content.split("\n")
        best_line_idx = 0
        for i, line in enumerate(lines):
            line_lower = line.lower()
            if any(t in line_lower for t in terms):
                best_line_idx = i
                break

        # Extract snippet: 5 lines around best match
        start = max(0, best_line_idx - 2)
        end = min(len(lines), best_line_idx + 3)
        snippet = "\n".join(lines[start:end]).strip()
        if len(snippet) > 700:
            snippet = snippet[:700] + "..."

        rel_path = os.path.relpath(fpath, mgr.workspace_dir)
        results.append({
            "path": rel_path,
            "snippet": snippet,
            "score": round(score, 3),
            "start_line": start + 1,
            "end_line": end,
            "source": "local",
            "matched_terms": matched_terms,
            "total_terms": len(terms),
        })

    # Sort by score descending, then by path (newer files first)
    results.sort(key=lambda r: (-r["score"], r["path"]))
    return results[:max_results]


def _search_longterm_memory(query: str, max_results: int = 5) -> List[Dict[str, Any]]:
    """Search AgentCore Memory for long-term recall."""
    try:
        from api.services.memory_sync import load_memory_config
        config = load_memory_config()
        memory_id = config.get("memory_id", "")
        region = config.get("memory_region", "us-west-2")
        enabled = config.get("memory_enabled", True)

        if not enabled or not memory_id:
            return []

        import boto3
        client = boto3.client("bedrock-agent-runtime", region_name=region)
        response = client.retrieve(
            knowledgeBaseId=memory_id,
            retrievalQuery={"text": query},
            retrievalConfiguration={
                "vectorSearchConfiguration": {
                    "numberOfResults": max_results,
                }
            },
        )

        results = []
        for item in response.get("retrievalResults", []):
            content = item.get("content", {}).get("text", "")
            score = item.get("score", 0)
            location = item.get("location", {})
            source_uri = location.get("s3Location", {}).get("uri", "")

            if content:
                results.append({
                    "snippet": content[:700],
                    "score": round(score, 3) if score else 0,
                    "source": "agentcore",
                    "source_uri": source_uri,
                    "path": source_uri.split("/")[-1] if source_uri else "",
                })

        return results
    except Exception as e:
        logger.warning(f"AgentCore memory search failed: {e}")
        return []


def memory_search(query: str, scope: str = "auto", max_results: int = 10, days: int = None) -> Dict[str, Any]:
    """Search memory across local files and AgentCore.

    Args:
        query: Search query text
        scope: "auto" (recent first, then longterm), "recent" (local files only), "longterm" (AgentCore only)
        max_results: Maximum results to return
        days: Override retention days for recent search

    Returns:
        Dict with results list, scope used, and metadata
    """
    if not query or not query.strip():
        return {"results": [], "scope": scope, "error": "Empty query"}

    query = query.strip()
    all_results: List[Dict[str, Any]] = []

    if scope in ("auto", "recent"):
        recent = _search_recent_memory(query, max_results=max_results, days=days)
        all_results.extend(recent)

    if scope in ("auto", "longterm"):
        # In auto mode, only search longterm if recent results are insufficient
        if scope == "auto" and len(all_results) >= max_results:
            pass  # enough results from recent
        else:
            remaining = max_results - len(all_results)
            if remaining > 0:
                longterm = _search_longterm_memory(query, max_results=remaining)
                all_results.extend(longterm)

    # Deduplicate and sort by score
    all_results.sort(key=lambda r: -r.get("score", 0))
    all_results = all_results[:max_results]

    return {
        "query": query,
        "scope": scope,
        "results": all_results,
        "count": len(all_results),
        "sources": list(set(r.get("source", "unknown") for r in all_results)),
    }


def memory_get(path: str, from_line: int = None, lines: int = None) -> Dict[str, Any]:
    """Read a specific memory file.

    Args:
        path: Relative path within workspace (e.g., "MEMORY.md", "memory/2026-02-26.md")
        from_line: Optional start line (1-based)
        lines: Optional number of lines to read

    Returns:
        Dict with text content and path
    """
    mgr = _get_memory_file_manager()
    if mgr is None:
        return {"error": "Memory file manager not initialized", "text": "", "path": path}

    return mgr.read_file(path, from_line=from_line, lines=lines)
