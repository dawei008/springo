"""
Skill Loader for Springo
Based on Anthropic's Agent Skills standard (agentskills.io)

Skills are folders containing a SKILL.md file with:
- YAML frontmatter (name, description)
- Markdown instructions for Claude to follow
"""

import os
import re
import yaml
from pathlib import Path
from typing import Dict, List, Optional

class Skill:
    """Represents a loaded skill"""
    def __init__(self, name: str, description: str, instructions: str, path: str):
        self.name = name
        self.description = description
        self.instructions = instructions
        self.path = path
        self.resources = {}  # Additional resources (scripts, templates, etc.)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "instructions": self.instructions,
            "path": self.path,
            "has_resources": bool(self.resources)
        }

class SkillLoader:
    """Loads and manages skills from the skills directory"""

    def __init__(self, skills_dir: str = None):
        if skills_dir is None:
            # Default to skills directory relative to this file
            skills_dir = os.path.join(os.path.dirname(__file__), "skills")
        self.skills_dir = Path(skills_dir)
        self.skills: Dict[str, Skill] = {}
        self._load_all_skills()

    def _parse_skill_md(self, content: str) -> tuple:
        """Parse SKILL.md content into frontmatter and instructions"""
        # Match YAML frontmatter between --- markers
        frontmatter_pattern = r'^---\s*\n(.*?)\n---\s*\n(.*)$'
        match = re.match(frontmatter_pattern, content, re.DOTALL)

        if match:
            frontmatter_str = match.group(1)
            instructions = match.group(2).strip()
            try:
                frontmatter = yaml.safe_load(frontmatter_str)
            except yaml.YAMLError:
                frontmatter = {}
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

            skill = Skill(
                name=name,
                description=description,
                instructions=instructions,
                path=str(skill_path)
            )

            # Load additional resources (scripts, templates, etc.)
            for resource_file in skill_path.iterdir():
                if resource_file.name != 'SKILL.md' and resource_file.is_file():
                    try:
                        if resource_file.suffix in ['.py', '.js', '.md', '.txt', '.json', '.yaml', '.yml']:
                            skill.resources[resource_file.name] = resource_file.read_text(encoding='utf-8')
                    except Exception:
                        pass

            return skill
        except Exception as e:
            print(f"Error loading skill from {skill_path}: {e}")
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

    def reload(self):
        """Reload all skills from disk"""
        self._load_all_skills()

    def list_skills(self) -> List[dict]:
        """List all available skills"""
        return [skill.to_dict() for skill in self.skills.values()]

    def get_skill(self, name: str) -> Optional[Skill]:
        """Get a skill by name"""
        return self.skills.get(name)

    def get_skill_instructions(self, name: str) -> Optional[str]:
        """Get the instructions for a skill"""
        skill = self.get_skill(name)
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

        prompt = f"""<skill name="{skill.name}">
{skill.instructions}
</skill>

User request: {user_request}

Please follow the skill instructions above to complete this task."""

        return prompt


# Global skill loader instance
_skill_loader: Optional[SkillLoader] = None

def get_skill_loader(skills_dir: str = None) -> SkillLoader:
    """Get or create the global skill loader instance"""
    global _skill_loader
    if _skill_loader is None:
        _skill_loader = SkillLoader(skills_dir)
    return _skill_loader


if __name__ == "__main__":
    # Test the skill loader
    loader = SkillLoader()
    print(f"Skills directory: {loader.skills_dir}")
    print(f"Loaded skills: {list(loader.skills.keys())}")

    for skill in loader.list_skills():
        print(f"\n{skill['name']}: {skill['description'][:50]}...")
