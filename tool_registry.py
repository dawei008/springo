"""
Tool Registry for Lazy Loading MCP Tools

Similar to Claude Code's ToolSearch mechanism:
- Deferred tools: Registered but not loaded, only metadata available
- Active tools: Fully loaded and available for use

This saves context by only sending active tools to Claude.
"""

import logging
from typing import Any, Dict, List, Optional, Set
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

        # Exact name match
        if query_lower == self.name.lower():
            return 1.0

        # Name contains query
        if query_lower in self.name.lower():
            score = max(score, 0.8)

        # Query contains name
        if self.name.lower() in query_lower:
            score = max(score, 0.7)

        # Description match
        if query_lower in self.description.lower():
            score = max(score, 0.5)

        # Keyword match
        for keyword in self.keywords:
            if query_lower in keyword.lower() or keyword.lower() in query_lower:
                score = max(score, 0.6)

        # Word overlap
        query_words = set(query_lower.split())
        name_words = set(self.name.lower().replace('-', ' ').replace('_', ' ').split())
        desc_words = set(self.description.lower().split())

        name_overlap = len(query_words & name_words) / max(len(query_words), 1)
        desc_overlap = len(query_words & desc_words) / max(len(query_words), 1)

        score = max(score, name_overlap * 0.7, desc_overlap * 0.4)

        return score


class ToolRegistry:
    """
    Manages deferred and active tools for lazy loading.

    Usage:
        registry = ToolRegistry()

        # Register deferred tools (metadata only)
        registry.register_deferred("server__tool", "Description", "server")

        # Search for tools
        results = registry.search("query")

        # Activate a tool (load full definition)
        registry.activate("server__tool", full_definition)

        # Get active tools for Claude
        active_tools = registry.get_active_tools()
    """

    def __init__(self):
        self._deferred: Dict[str, DeferredTool] = {}
        self._active: Dict[str, Dict[str, Any]] = {}
        self._tool_loaders: Dict[str, callable] = {}  # server_name -> loader function

    def register_deferred(self, name: str, description: str, server_name: str,
                          keywords: List[str] = None):
        """Register a tool as deferred (metadata only)"""
        if name not in self._active:  # Don't register if already active
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
        """
        Activate a deferred tool, making it available for use.

        If definition is not provided, tries to load it using registered loader.
        """
        if tool_name in self._active:
            return True  # Already active

        if tool_name not in self._deferred:
            logger.warning(f"Tool {tool_name} not found in deferred registry")
            return False

        deferred = self._deferred[tool_name]

        # Try to get definition
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

        # Move from deferred to active
        self._active[tool_name] = definition
        del self._deferred[tool_name]
        logger.info(f"Activated tool: {tool_name}")
        return True

    def deactivate(self, tool_name: str):
        """Deactivate a tool, moving it back to deferred state"""
        if tool_name in self._active:
            definition = self._active[tool_name]
            # Re-register as deferred
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

        Returns list of matching tools with relevance scores.
        """
        results = []

        # Handle direct selection
        if query.startswith("select:"):
            tool_name = query[7:].strip()

            # Check active tools
            if tool_name in self._active:
                return [{
                    "name": tool_name,
                    "description": self._active[tool_name].get('description', ''),
                    "status": "active",
                    "score": 1.0
                }]

            # Check deferred tools
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

        # Keyword search in deferred tools
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

        # Also search in active tools
        for name, definition in self._active.items():
            desc = definition.get('description', '')
            # Simple scoring for active tools
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

        # Sort by score and limit results
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
        """Check if a tool is active"""
        return tool_name in self._active

    def is_deferred(self, tool_name: str) -> bool:
        """Check if a tool is deferred"""
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
