"""
Skills Blueprint
Skill management endpoints
"""

import os
import logging
from flask import Blueprint

from skill_loader import get_skill_loader
from .shared import json_response

logger = logging.getLogger(__name__)

skills_bp = Blueprint('skills', __name__)


@skills_bp.route('/v1/skills', methods=['GET'])
def list_skills():
    """List all available skills"""
    try:
        loader = get_skill_loader()
        skills = []
        for skill in loader.skills.values():
            skills.append({
                "name": skill.name,
                "description": skill.description,
                "triggers": skill.triggers,
            })
        return json_response({"skills": skills, "count": len(skills)})
    except Exception as e:
        logger.error(f"List skills error: {e}")
        return json_response({"error": str(e)}, status=500)


@skills_bp.route('/v1/skills/<skill_name>', methods=['GET'])
def get_skill(skill_name: str):
    """Get a specific skill"""
    try:
        loader = get_skill_loader()
        skill = loader.get_skill(skill_name)

        if not skill:
            return json_response({"error": f"Skill '{skill_name}' not found"}, status=404)

        return json_response({
            "name": skill.name,
            "description": skill.description,
            "triggers": skill.triggers,
            "instructions": skill.instructions,
        })
    except Exception as e:
        logger.error(f"Get skill error: {e}")
        return json_response({"error": str(e)}, status=500)


@skills_bp.route('/v1/skills/<skill_name>/instructions', methods=['GET'])
def get_skill_instructions(skill_name: str):
    """Get skill instructions"""
    try:
        loader = get_skill_loader()
        skill = loader.get_skill(skill_name)

        if not skill:
            return json_response({"error": f"Skill '{skill_name}' not found"}, status=404)

        return json_response({
            "name": skill.name,
            "instructions": skill.instructions,
        })
    except Exception as e:
        logger.error(f"Get skill instructions error: {e}")
        return json_response({"error": str(e)}, status=500)


@skills_bp.route('/v1/skills/reload', methods=['POST'])
def reload_skills():
    """Reload skills from disk"""
    try:
        loader = get_skill_loader()
        loader.reload()
        skills = [s.name for s in loader.skills.values()]
        return json_response({"success": True, "skills": skills, "count": len(skills)})
    except Exception as e:
        logger.error(f"Reload skills error: {e}")
        return json_response({"error": str(e)}, status=500)


@skills_bp.route('/v1/skills/path', methods=['GET'])
def get_skills_path():
    """Get skills directory path"""
    try:
        loader = get_skill_loader()
        return json_response({"path": loader.skills_dir})
    except Exception as e:
        logger.error(f"Get skills path error: {e}")
        return json_response({"error": str(e)}, status=500)
