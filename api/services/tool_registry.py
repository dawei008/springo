"""
Tool Registry for Lazy Loading MCP Tools

Similar to Claude Code's ToolSearch mechanism:
- Deferred tools: Registered but not loaded, only metadata available
- Active tools: Fully loaded and available for use

This saves context by only sending active tools to Claude.
"""

import logging
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class DeferredTool:
    """Metadata for a deferred (not yet loaded) tool"""
    name: str
    description: str
    server_name: str  # MCP server this tool belongs to
    keywords: List[str] = field(default_factory=list)

    def matches_query(self, query: str) -> float:
        """Return relevance score (0-1) for a search query"""
        query_lower = query.lower()
        score = 0.0

        # Normalize name for matching (handle __, -, _)
        name_lower = self.name.lower()
        name_normalized = name_lower.replace('__', ' ').replace('-', ' ').replace('_', ' ')

        # Exact name match
        if query_lower == name_lower:
            return 1.0

        # Name contains entire query
        if query_lower in name_lower or query_lower in name_normalized:
            score = max(score, 0.9)

        # Query contains entire name
        if name_lower in query_lower:
            score = max(score, 0.7)

        # Split query into words for multi-word matching
        query_words = set(query_lower.split())
        name_words = set(name_normalized.split())
        desc_lower = self.description.lower()

        # Count how many query words appear in name
        name_matches = sum(1 for w in query_words if w in name_normalized or any(w in nw for nw in name_words))
        if name_matches > 0:
            name_score = (name_matches / len(query_words)) * 0.85
            if name_matches == len(query_words):
                name_score = 0.9
            score = max(score, name_score)

        # Count how many query words appear in description
        desc_matches = sum(1 for w in query_words if w in desc_lower)
        if desc_matches > 0:
            desc_score = (desc_matches / len(query_words)) * 0.6
            if desc_matches == len(query_words):
                desc_score = 0.7
            score = max(score, desc_score)

        # Keyword match (for registered keywords)
        for keyword in self.keywords:
            if len(keyword) < 3:
                continue
            keyword_lower = keyword.lower()
            if keyword_lower in query_words or any(keyword_lower == qw for qw in query_words):
                score = max(score, 0.65)
            for qw in query_words:
                if len(qw) >= 3 and (qw == keyword_lower or keyword_lower.startswith(qw) or qw.startswith(keyword_lower)):
                    score = max(score, 0.5)

        return score


class ToolRegistry:
    """
    Manages deferred and active tools for lazy loading.

    Usage:
        registry = ToolRegistry()
        registry.register_deferred("server__tool", "Description", "server")
        results = registry.search("query")
        registry.activate("server__tool", full_definition)
        active_tools = registry.get_active_tools()
    """

    def __init__(self):
        self._deferred: Dict[str, DeferredTool] = {}
        self._active: Dict[str, Dict[str, Any]] = {}
        self._tool_loaders: Dict[str, callable] = {}

    def register_deferred(self, name: str, description: str, server_name: str,
                          keywords: List[str] = None):
        """Register a tool as deferred (metadata only)"""
        if name not in self._active:
            self._deferred[name] = DeferredTool(
                name=name,
                description=description,
                server_name=server_name,
                keywords=keywords or []
            )

    def register_tool_loader(self, server_name: str, loader: callable):
        """Register a function that can load tool definitions for a server"""
        self._tool_loaders[server_name] = loader

    def activate(self, tool_name: str, definition: Dict[str, Any] = None) -> bool:
        """Activate a deferred tool, making it available for use."""
        if tool_name in self._active:
            return True

        if tool_name not in self._deferred:
            logger.warning(f"Tool {tool_name} not found in deferred registry")
            return False

        deferred = self._deferred[tool_name]

        if definition is None:
            loader = self._tool_loaders.get(deferred.server_name)
            if loader:
                try:
                    definition = loader(tool_name)
                except Exception as e:
                    logger.error(f"Failed to load tool {tool_name}: {e}")
                    return False

        if definition is None:
            logger.error(f"No definition available for tool {tool_name}")
            return False

        self._active[tool_name] = definition
        del self._deferred[tool_name]
        logger.info(f"Activated tool: {tool_name}")
        return True

    def deactivate(self, tool_name: str):
        """Deactivate a tool, moving it back to deferred state"""
        if tool_name in self._active:
            definition = self._active[tool_name]
            self._deferred[tool_name] = DeferredTool(
                name=tool_name,
                description=definition.get('description', ''),
                server_name=tool_name.split('__')[0] if '__' in tool_name else 'unknown',
                keywords=[]
            )
            del self._active[tool_name]
            logger.info(f"Deactivated tool: {tool_name}")

    def search(self, query: str, max_results: int = 5) -> List[Dict[str, Any]]:
        """
        Search for tools matching a query.

        Query formats:
        - "select:tool_name" - Direct selection of a specific tool
        - "keyword query" - Search by keywords
        """
        # Handle direct selection
        if query.startswith("select:"):
            tool_name = query[7:].strip()
            if tool_name in self._active:
                return [{
                    "name": tool_name,
                    "description": self._active[tool_name].get('description', ''),
                    "status": "active",
                    "score": 1.0
                }]
            if tool_name in self._deferred:
                deferred = self._deferred[tool_name]
                return [{
                    "name": tool_name,
                    "description": deferred.description,
                    "status": "deferred",
                    "server": deferred.server_name,
                    "score": 1.0
                }]
            return []

        # Keyword search
        scored_results = []
        for name, deferred in self._deferred.items():
            score = deferred.matches_query(query)
            if score > 0.1:
                scored_results.append({
                    "name": name,
                    "description": deferred.description[:200] + "..." if len(deferred.description) > 200 else deferred.description,
                    "status": "deferred",
                    "server": deferred.server_name,
                    "score": score
                })

        for name, definition in self._active.items():
            desc = definition.get('description', '')
            query_lower = query.lower()
            score = 0.0
            if query_lower in name.lower():
                score = 0.8
            elif query_lower in desc.lower():
                score = 0.5
            if score > 0.1:
                scored_results.append({
                    "name": name,
                    "description": desc[:200] + "..." if len(desc) > 200 else desc,
                    "status": "active",
                    "score": score
                })

        scored_results.sort(key=lambda x: x['score'], reverse=True)
        return scored_results[:max_results]

    def get_active_tools(self) -> List[Dict[str, Any]]:
        """Get all active tool definitions"""
        return list(self._active.values())

    def get_deferred_tools(self) -> List[Dict[str, str]]:
        """Get list of deferred tool names and descriptions"""
        return [
            {"name": name, "description": tool.description, "server": tool.server_name}
            for name, tool in self._deferred.items()
        ]

    def get_all_tool_names(self) -> Dict[str, List[str]]:
        """Get all tool names organized by status"""
        return {
            "active": list(self._active.keys()),
            "deferred": list(self._deferred.keys())
        }

    def is_active(self, tool_name: str) -> bool:
        return tool_name in self._active

    def is_deferred(self, tool_name: str) -> bool:
        return tool_name in self._deferred

    def clear(self):
        """Clear all registered tools"""
        self._deferred.clear()
        self._active.clear()


# Singleton instance
_registry: Optional[ToolRegistry] = None


def get_tool_registry() -> ToolRegistry:
    """Get the singleton tool registry instance"""
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
    return _registry


__all__ = [
    'DeferredTool', 'ToolRegistry', 'get_tool_registry',
]
