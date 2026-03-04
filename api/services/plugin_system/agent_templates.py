"""
Agent Template Manager for Springo Plugin System

Loads agent templates from ~/.springo/agents/ and plugin directories.
Templates define reusable agent profiles (model, system prompt, tools, etc.)
that can be used when spawning team workers.
"""
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class AgentTemplate:
    """A parsed agent template."""

    def __init__(self, raw: Dict[str, Any], path: str = ""):
        self.name: str = raw["name"]
        self.role: str = raw.get("role", self.name)
        self.description: str = raw.get("description", "")
        self.model: str = raw.get("model", "")
        self.system_prompt: str = raw.get("system_prompt", "")
        self.tools: List[str] = raw.get("tools", [])
        self.max_tokens: int = raw.get("max_tokens", 4096)
        self.temperature: float = raw.get("temperature", 0.7)
        self.metadata: Dict[str, Any] = raw.get("metadata", {})
        self.path = path

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "role": self.role,
            "description": self.description,
            "model": self.model,
            "system_prompt": self.system_prompt[:200] + "..." if len(self.system_prompt) > 200 else self.system_prompt,
            "tools": self.tools,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "metadata": self.metadata,
            "path": self.path,
        }


class AgentTemplateManager:
    """Loads and manages agent templates from ~/.springo/agents/."""

    def __init__(self, agents_dir: str = None):
        if agents_dir is None:
            agents_dir = os.path.expanduser("~/.springo/agents")
        self.agents_dir = Path(agents_dir)
        self._templates: Dict[str, AgentTemplate] = {}
        self._loaded = False

    def load_templates(self) -> int:
        """Scan agents directory and load all templates. Returns count."""
        self._templates = {}

        if not self.agents_dir.exists():
            self.agents_dir.mkdir(parents=True, exist_ok=True)
            self._loaded = True
            return 0

        for f in sorted(self.agents_dir.iterdir()):
            if f.suffix != ".json" or not f.is_file():
                continue
            try:
                with open(f, "r", encoding="utf-8") as fh:
                    raw = json.load(fh)
                if "name" not in raw:
                    logger.warning(f"Agent template missing 'name': {f}")
                    continue
                tmpl = AgentTemplate(raw, path=str(f))
                self._templates[tmpl.name] = tmpl
            except Exception as e:
                logger.error(f"Failed to load agent template {f.name}: {e}")

        self._loaded = True
        if self._templates:
            logger.info(f"Loaded {len(self._templates)} agent template(s)")
        return len(self._templates)

    def list_templates(self) -> List[Dict[str, Any]]:
        if not self._loaded:
            self.load_templates()
        return [t.to_dict() for t in self._templates.values()]

    def get_template(self, name: str) -> Optional[AgentTemplate]:
        if not self._loaded:
            self.load_templates()
        return self._templates.get(name)

    def reload(self) -> int:
        self._loaded = False
        return self.load_templates()


# -- singleton --

_manager: Optional[AgentTemplateManager] = None


def get_agent_template_manager() -> AgentTemplateManager:
    global _manager
    if _manager is None:
        _manager = AgentTemplateManager()
    return _manager
