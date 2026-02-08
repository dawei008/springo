"""
Skills Router for FastAPI
技能管理端点
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Any, Dict, List, Optional
import os
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

router = APIRouter()

# Skills 目录
SKILLS_DIR = Path(os.path.expanduser("~/.springo/skills"))

# Active skill state (consumed once per auto-loop iteration)
_active_skill: Optional[Dict[str, Any]] = None


def set_active_skill(skill_info: Dict[str, Any]):
    """Set active skill - will be injected into next system prompt"""
    global _active_skill
    _active_skill = skill_info


def consume_active_skill() -> Optional[Dict[str, Any]]:
    """Get and clear active skill (one-time consumption for injection)"""
    global _active_skill
    skill = _active_skill
    _active_skill = None
    return skill


class SkillInfo(BaseModel):
    """技能信息"""
    name: str
    description: str = ""
    path: str = ""
    loaded: bool = False
    has_resources: bool = False
    triggers: List[str] = []


class SkillsListResponse(BaseModel):
    """技能列表响应"""
    skills: List[SkillInfo]
    total: int
    path: str


class SkillDetailResponse(BaseModel):
    """技能详情响应"""
    name: str
    description: str = ""
    instructions: str = ""
    path: str = ""
    files: List[str] = []
    has_resources: bool = False


class SkillInstructionsResponse(BaseModel):
    """技能指令响应"""
    name: str
    instructions: str


class ReloadResponse(BaseModel):
    """重载响应"""
    status: str
    message: str
    count: int = 0


class ActivateSkillRequest(BaseModel):
    """技能激活请求"""
    name: str
    user_request: str = ""


def _get_loader():
    """Lazy import skill loader to avoid circular imports"""
    from ..services.skill_loader import get_skill_loader
    return get_skill_loader()


@router.get("/skills", response_model=SkillsListResponse)
async def list_skills():
    """列出所有可用技能"""
    loader = _get_loader()
    skills_data = loader.list_skills()
    skills = [
        SkillInfo(
            name=s["name"],
            description=s.get("description", ""),
            path=s.get("path", ""),
            loaded=True,
            has_resources=s.get("has_resources", False),
            triggers=s.get("triggers", []),
        )
        for s in skills_data
    ]
    return SkillsListResponse(
        skills=skills,
        total=len(skills),
        path=str(SKILLS_DIR)
    )


@router.get("/skills/{skill_name}", response_model=SkillDetailResponse)
async def get_skill(skill_name: str):
    """获取技能详情"""
    loader = _get_loader()
    skill = loader.get_skill(skill_name)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill not found: {skill_name}")

    # List files in skill directory
    files = []
    skill_path = Path(skill.path)
    if skill_path.exists():
        for f in skill_path.rglob("*"):
            if f.is_file():
                files.append(str(f.relative_to(skill_path)))

    return SkillDetailResponse(
        name=skill.name,
        description=skill.description,
        instructions=skill.instructions,
        path=skill.path,
        files=files[:50],
        has_resources=bool(skill.resources),
    )


@router.get("/skills/{skill_name}/instructions", response_model=SkillInstructionsResponse)
async def get_skill_instructions(skill_name: str):
    """获取技能指令内容"""
    loader = _get_loader()
    instructions = loader.get_skill_instructions(skill_name)
    if instructions is None:
        raise HTTPException(status_code=404, detail=f"Skill not found: {skill_name}")
    return SkillInstructionsResponse(name=skill_name, instructions=instructions)


@router.get("/skills/{skill_name}/resources/{resource_name}")
async def get_skill_resource(skill_name: str, resource_name: str):
    """获取技能资源文件"""
    loader = _get_loader()
    content = loader.get_skill_resource(skill_name, resource_name)
    if content is None:
        raise HTTPException(status_code=404, detail=f"Resource not found: {skill_name}/{resource_name}")
    return {"name": resource_name, "skill": skill_name, "content": content}


@router.post("/skills/{skill_name}/prompt")
async def create_skill_prompt(skill_name: str, request: ActivateSkillRequest = None):
    """生成包含技能指令的完整 prompt"""
    loader = _get_loader()
    user_request = request.user_request if request else ""
    prompt = loader.create_skill_prompt(skill_name, user_request)
    if prompt is None:
        raise HTTPException(status_code=404, detail=f"Skill not found: {skill_name}")
    return {"skill": skill_name, "prompt": prompt}


@router.post("/skills/reload", response_model=ReloadResponse)
async def reload_skills():
    """重新加载所有技能"""
    try:
        loader = _get_loader()
        loader.force_reload()
        count = len(loader.skills)
        return ReloadResponse(
            status="ok",
            message=f"Reloaded {count} skills",
            count=count
        )
    except Exception as e:
        logger.error(f"Error reloading skills: {e}")
        return ReloadResponse(status="error", message=str(e), count=0)


@router.post("/skills/{skill_name}/activate")
async def activate_skill(skill_name: str, request: ActivateSkillRequest = None):
    """激活技能（注入到下一次 auto-loop 的 system prompt）"""
    loader = _get_loader()
    skill = loader.get_skill(skill_name)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill not found: {skill_name}")

    skill_info = {
        "name": skill.name,
        "instructions": skill.instructions,
        "user_request": request.user_request if request else "",
    }
    set_active_skill(skill_info)
    return {"success": True, "skill_name": skill_name}


@router.get("/skills/path")
async def get_skills_path():
    """获取技能目录路径"""
    return {"path": str(SKILLS_DIR)}
