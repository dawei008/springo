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


def _load_agentcore_config() -> Dict[str, Any]:
    """Load AgentCore memory config from ~/.springo/config.json."""
    import json as _json
    config_path = os.path.expanduser("~/.springo/config.json")
    if not os.path.exists(config_path):
        return {}
    with open(config_path, "r", encoding="utf-8") as f:
        full = _json.load(f)
    return full.get("memory", {})


def _get_strategies() -> List[Dict[str, Any]]:
    """Get configured LTM strategies with namespace info."""
    mem_cfg = _load_agentcore_config()
    return mem_cfg.get("ltm", {}).get("strategies", [])


def _detect_strategy_type(namespace: str) -> str:
    """Infer strategy type from namespace string."""
    if "ConversationFacts" in namespace or "Fact" in namespace:
        return "SEMANTIC"
    if "UserPreferences" in namespace or "Preference" in namespace:
        return "USER_PREFERENCE"
    if "ConversationSummary" in namespace or "Summary" in namespace:
        return "SUMMARIZATION"
    if "ConversationEpisodes" in namespace or "Episode" in namespace:
        return "EPISODIC"
    return "UNKNOWN"


def _search_longterm_memory(query: str, max_results: int = 5) -> List[Dict[str, Any]]:
    """Search AgentCore Memory for long-term recall.

    Uses bedrock-agentcore data-plane client with retrieve_memory_records API.
    Searches across all configured strategy namespaces and merges by score.
    """
    try:
        mem_cfg = _load_agentcore_config()
        memory_id = mem_cfg.get("memory_id", "")
        region = mem_cfg.get("memory_region", "us-west-2")
        enabled = mem_cfg.get("memory_enabled", True)

        if not enabled or not memory_id:
            return []

        strategies = _get_strategies()
        if not strategies:
            logger.warning("AgentCore memory: no strategies configured")
            return []

        import boto3
        client = boto3.client("bedrock-agentcore", region_name=region)

        all_results: List[Dict[str, Any]] = []
        for strategy in strategies:
            namespace = strategy.get("namespace", "")
            strategy_id = strategy.get("id", "")
            if not namespace:
                continue

            try:
                search_criteria: Dict[str, Any] = {
                    "searchQuery": query,
                    "topK": max_results,
                }
                if strategy_id:
                    search_criteria["memoryStrategyId"] = strategy_id

                response = client.retrieve_memory_records(
                    memoryId=memory_id,
                    namespace=namespace,
                    searchCriteria=search_criteria,
                    maxResults=max_results,
                )

                for r in response.get("memoryRecordSummaries", []):
                    content_text = r.get("content", {}).get("text", "")
                    if not content_text:
                        continue
                    namespaces = r.get("namespaces", [])
                    ns = namespaces[0] if namespaces else namespace
                    all_results.append({
                        "snippet": content_text[:700],
                        "score": round(r.get("score", 0), 3),
                        "source": "agentcore",
                        "strategy_type": _detect_strategy_type(ns),
                        "namespace": ns,
                        "created_at": str(r.get("createdAt", "")),
                    })
            except Exception as e:
                logger.debug(f"AgentCore search failed for namespace {namespace}: {e}")
                continue

        # Sort by score descending and return top results
        all_results.sort(key=lambda x: -x.get("score", 0))
        return all_results[:max_results]
    except Exception as e:
        logger.warning(f"AgentCore memory search failed: {e}")
        return []


def _list_memory_files() -> Dict[str, Any]:
    """List all local memory files with metadata."""
    mgr = _get_memory_file_manager()
    if mgr is None:
        return {"files": [], "error": "Memory file manager not initialized"}

    files = mgr.list_files()
    # Also check MEMORY.md
    memory_md_exists = os.path.isfile(mgr.memory_md_path)
    memory_md_size = os.path.getsize(mgr.memory_md_path) if memory_md_exists else 0

    return {
        "scope": "list",
        "memory_md": {"exists": memory_md_exists, "size": memory_md_size, "path": "MEMORY.md"},
        "files": files,
        "count": len(files),
        "base_path": mgr.workspace_dir,
    }


def memory_search(query: str, scope: str = "auto", max_results: int = 10, days: int = None) -> Dict[str, Any]:
    """Search memory across local files and AgentCore.

    Args:
        query: Search query text (ignored when scope='list')
        scope: "auto", "recent", "longterm", or "list"
        max_results: Maximum results to return
        days: Override retention days for recent search

    Returns:
        Dict with results list, scope used, and metadata
    """
    if scope == "list":
        return _list_memory_files()

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


# Valid memory types for categorized entries
VALID_MEMORY_TYPES = ("user", "feedback", "project", "reference")


def memory_write(target: str, content: str, memory_type: str = None) -> Dict[str, Any]:
    """Write content to memory files.

    Args:
        target: Where to write — "daily" (append to today's log) or "longterm" (overwrite MEMORY.md)
        content: Content to write (Markdown text)
        memory_type: Optional category tag — "user", "feedback", "project", or "reference".
                     When provided, the entry is prefixed with a type tag for better
                     distillation into typed MEMORY.md sections.

    Returns:
        Dict with success status and file path
    """
    if not content or not content.strip():
        return {"error": "Empty content", "target": target}

    mgr = _get_memory_file_manager()
    if mgr is None:
        return {"error": "Memory file manager not initialized", "target": target}

    target = target.strip().lower()

    # Validate and apply memory_type tag
    if memory_type:
        memory_type = memory_type.strip().lower()
        if memory_type not in VALID_MEMORY_TYPES:
            return {"error": f"Invalid memory_type '{memory_type}'. Use one of: {', '.join(VALID_MEMORY_TYPES)}", "target": target}
        # Prefix content with type tag for downstream distillation
        content = f"[{memory_type}] {content}"

    if target == "daily":
        try:
            path = mgr.append_daily(content)
            rel_path = os.path.relpath(path, mgr.workspace_dir)
            return {"success": True, "target": "daily", "path": rel_path, "chars": len(content),
                    "memory_type": memory_type}
        except Exception as e:
            return {"error": str(e), "target": "daily"}

    elif target == "longterm":
        try:
            # Read existing MEMORY.md and append (don't blindly overwrite)
            existing = mgr.read_memory_md()
            if existing.strip():
                updated = existing.rstrip("\n") + "\n\n" + content
            else:
                updated = content
            path = mgr.write_longterm(updated)
            rel_path = os.path.relpath(path, mgr.workspace_dir)
            return {"success": True, "target": "longterm", "path": rel_path, "chars": len(updated),
                    "memory_type": memory_type}
        except Exception as e:
            return {"error": str(e), "target": "longterm"}

    else:
        return {"error": f"Unknown target '{target}'. Use 'daily' or 'longterm'.", "target": target}


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
