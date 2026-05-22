"""
Skill Loader for Springo FastAPI
Based on Anthropic's Agent Skills standard (agentskills.io)

Skills are folders containing a SKILL.md file with:
- YAML frontmatter (name, description)
- Markdown instructions for Claude to follow
"""

import os
import re
import time
import logging
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Cache TTL in seconds
SKILL_CACHE_TTL = 60

# Try to import yaml; fall back to simple parsing if unavailable
try:
    import yaml
    HAS_YAML = True
except Exception as _yaml_err:
    yaml = None
    HAS_YAML = False
    logger.warning(f"PyYAML not available ({type(_yaml_err).__name__}: {_yaml_err}), using simple frontmatter parsing")


class Skill:
    """Represents a loaded skill"""
    def __init__(self, name: str, description: str, instructions: str, path: str,
                 triggers: List[str] = None, source: str = "agent-created"):
        self.name = name
        self.description = description
        self.instructions = instructions
        self.path = path
        self.triggers: List[str] = triggers or []
        self.source = source
        self.resources: Dict[str, str] = {}

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "instructions": self.instructions,
            "path": self.path,
            "has_resources": bool(self.resources),
            "triggers": self.triggers,
            "source": self.source,
        }


class SkillLoader:
    """Loads and manages skills from the skills directory"""

    def __init__(self, skills_dir: str = None):
        if skills_dir is None:
            skills_dir = os.path.expanduser("~/.springo/skills")
        self.skills_dir = Path(skills_dir)
        self.skills: Dict[str, Skill] = {}
        self._last_load_time = 0
        self._load_all_skills()

    def _parse_skill_md(self, content: str) -> tuple:
        """Parse SKILL.md content into frontmatter and instructions"""
        frontmatter_pattern = r'^---\s*\n(.*?)\n---\s*\n(.*)$'
        match = re.match(frontmatter_pattern, content, re.DOTALL)

        if match:
            frontmatter_str = match.group(1)
            instructions = match.group(2).strip()
            if HAS_YAML:
                try:
                    frontmatter = yaml.safe_load(frontmatter_str)
                except Exception as e:
                    logger.warning(f"YAML parse failed: {e}")
                    frontmatter = {}
            else:
                # Simple key: value parsing with basic multi-line block support
                frontmatter = {}
                current_key = None
                current_lines = []
                for line in frontmatter_str.split('\n'):
                    # Indented line = continuation of multi-line value
                    if current_key and line.startswith('  '):
                        current_lines.append(line.strip())
                        continue
                    # Save previous multi-line key
                    if current_key and current_lines:
                        frontmatter[current_key] = ' '.join(current_lines)
                        current_key = None
                        current_lines = []
                    if ':' in line and not line.startswith(' '):
                        key, _, value = line.partition(':')
                        key = key.strip()
                        value = value.strip().strip('"').strip("'")
                        if value in ('|', '>'):
                            # Multi-line block scalar — collect indented lines
                            current_key = key
                            current_lines = []
                        elif value.startswith('-') or value == '':
                            # List or empty — skip for simple parser
                            frontmatter[key] = value
                        else:
                            frontmatter[key] = value
                # Flush remaining multi-line key
                if current_key and current_lines:
                    frontmatter[current_key] = ' '.join(current_lines)
        else:
            frontmatter = {}
            instructions = content.strip()

        return frontmatter, instructions

    def _load_skill(self, skill_path: Path) -> Optional[Skill]:
        """Load a single skill from a directory"""
        skill_md = skill_path / "SKILL.md"
        if not skill_md.exists():
            return None

        try:
            content = skill_md.read_text(encoding='utf-8')
            frontmatter, instructions = self._parse_skill_md(content)

            name = frontmatter.get('name', skill_path.name)
            description = frontmatter.get('description', '')

            # If no description from frontmatter, extract from first non-empty line
            if not description:
                for line in instructions.split('\n'):
                    line = line.strip()
                    if line and not line.startswith('#'):
                        description = line[:200]
                        break

            # Inject skill path info
            skill_path_str = f"~/.springo/skills/{skill_path.name}"
            enhanced_instructions = f"""**Skill Location**: `{skill_path_str}`

When referencing files in this skill (scripts, templates, etc.), use the path above.
For example: `{skill_path_str}/html2pptx.md` or `{skill_path_str}/scripts/convert.py`

---

{instructions}"""

            triggers = frontmatter.get('triggers', [])
            if isinstance(triggers, str):
                triggers = [t.strip() for t in triggers.split(',')]

            source = frontmatter.get('source', 'agent-created')
            skill = Skill(
                name=name,
                description=description,
                instructions=enhanced_instructions,
                path=str(skill_path.resolve()),
                triggers=triggers,
                source=source,
            )

            # Load additional resources
            for resource_file in skill_path.iterdir():
                if resource_file.name != 'SKILL.md' and resource_file.is_file():
                    try:
                        if resource_file.suffix in ['.py', '.js', '.md', '.txt', '.json', '.yaml', '.yml']:
                            skill.resources[resource_file.name] = resource_file.read_text(encoding='utf-8')
                    except Exception:
                        pass

            return skill
        except Exception as e:
            logger.warning(f"Error loading skill from {skill_path}: {e}")
            return None

    def _load_all_skills(self):
        """Load all skills from the skills directory"""
        self.skills = {}
        if not self.skills_dir.exists():
            self.skills_dir.mkdir(parents=True, exist_ok=True)
            return
        for item in self.skills_dir.iterdir():
            if item.is_dir():
                skill = self._load_skill(item)
                if skill:
                    self.skills[skill.name] = skill
        self._last_load_time = time.time()

    def reload(self, force: bool = False):
        """Reload all skills from disk with caching."""
        if force:
            self._load_all_skills()
            return
        elapsed = time.time() - self._last_load_time
        if elapsed > SKILL_CACHE_TTL:
            self._load_all_skills()

    def force_reload(self):
        """Force reload all skills, bypassing cache"""
        self._load_all_skills()

    def list_skills(self) -> List[dict]:
        """List all available skills"""
        self.reload()
        return [skill.to_dict() for skill in self.skills.values()]

    def get_skill(self, name: str) -> Optional[Skill]:
        """Get a skill by name"""
        self.reload()
        return self.skills.get(name)

    def get_skill_instructions(self, name: str) -> Optional[str]:
        """Get the instructions for a skill"""
        skill = self.get_skill(name)
        if skill:
            self._record_use(skill.name)
        return skill.instructions if skill else None

    def get_skill_resource(self, name: str, resource_name: str) -> Optional[str]:
        """Get a resource file from a skill"""
        skill = self.get_skill(name)
        if skill:
            return skill.resources.get(resource_name)
        return None

    def create_skill_prompt(self, name: str, user_request: str = "") -> Optional[str]:
        """Create a full prompt that includes skill instructions"""
        skill = self.get_skill(name)
        if not skill:
            return None
        self._record_use(skill.name)
        return f"""<skill name="{skill.name}">
{skill.instructions}
</skill>

User request: {user_request}

Please follow the skill instructions above to complete this task."""

    @staticmethod
    def _record_use(skill_name: str) -> None:
        """Bump the per-skill usage counter (~/.springo/skills/_usage.json).

        Lazy import so a circular import between skill_loader and
        skill_distiller doesn't deadlock at module-init time. Failures here
        are non-fatal — usage tracking is observability, not correctness.
        """
        try:
            from .skill_distiller import record_skill_use
            record_skill_use(skill_name)
        except Exception:
            pass


# Global skill loader instance
_skill_loader: Optional[SkillLoader] = None


def get_skill_loader(skills_dir: str = None) -> SkillLoader:
    """Get or create the global skill loader instance"""
    global _skill_loader
    if _skill_loader is None:
        _skill_loader = SkillLoader(skills_dir)
    return _skill_loader


__all__ = [
    'Skill', 'SkillLoader', 'get_skill_loader', 'SKILL_CACHE_TTL',
]
