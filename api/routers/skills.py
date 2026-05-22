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


@router.get("/skills/path")
async def get_skills_path():
    """获取技能目录路径"""
    return {"path": str(SKILLS_DIR)}


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


# ============ Skill Evaluation ============

class EvalRequest(BaseModel):
    max_samples: int = 10
    use_llm: bool = True
    judge_model: str = "claude-haiku-4-5-20251001"


@router.post("/skills/{skill_name}/evaluate")
async def evaluate_skill_endpoint(skill_name: str, request: EvalRequest = None):
    """Evaluate a skill's effectiveness by mining session history."""
    try:
        from ..services.skill_evaluator import evaluate_skill
    except ImportError:
        raise HTTPException(status_code=501, detail="Skill evaluator not available")

    req = request or EvalRequest()

    vendor_router = None
    if req.use_llm:
        try:
            from ..services.vendor_router import get_vendor_router
            vendor_router = get_vendor_router()
        except Exception:
            pass

    result = await evaluate_skill(
        skill_name=skill_name,
        max_samples=req.max_samples,
        use_llm=req.use_llm,
        vendor_router=vendor_router,
        judge_model=req.judge_model,
    )

    return {
        "skill_name": result.skill_name,
        "usage_count": result.usage_count,
        "sampled_count": result.sampled_count,
        "avg_correctness": result.avg_correctness,
        "avg_procedure_following": result.avg_procedure_following,
        "avg_conciseness": result.avg_conciseness,
        "overall_score": result.overall_score,
        "keyword_proxy_score": result.keyword_proxy_score,
        "evaluated_at": result.evaluated_at,
    }


@router.get("/skills/{skill_name}/evaluation")
async def get_skill_evaluation(skill_name: str):
    """Get cached evaluation results for a skill."""
    try:
        from ..services.skill_evaluator import load_eval_result
    except ImportError:
        raise HTTPException(status_code=501, detail="Skill evaluator not available")

    result = load_eval_result(skill_name)
    if not result:
        raise HTTPException(status_code=404, detail=f"No evaluation found for skill: {skill_name}")

    from dataclasses import asdict
    return asdict(result)




# ============ Skill Distill (daily auto-extraction) ============
# Mounted under /skill-distill/* (NOT /skills/distill/*) so the parameterized
# /skills/{skill_name}/... routes don't shadow these by matching "distill" as
# a skill name.

@router.get("/skill-distill/status")
async def distill_status():
    """Where the daily skill-distill loop stands."""
    from ..services.skill_distiller import get_status
    return get_status()


@router.post("/skill-distill/run")
async def distill_run(force: bool = False):
    """Manually kick the distill pass. `force=true` re-evaluates every session
    regardless of watermark (useful to bootstrap an existing corpus)."""
    from ..services.skill_distiller import run_distill_pass
    return await run_distill_pass(force=force)


@router.get("/skill-distill/usage")
async def skill_usage():
    """Per-skill usage counter. Records bumped each time a skill is injected
    into a chat via skill_loader.create_skill_prompt or get_skill_instructions."""
    from ..services.skill_distiller import _load_usage  # type: ignore
    return {"usage": _load_usage()}


@router.post("/skill-distill/gc")
async def distill_gc(grace_days: int = 14):
    """Run only the auto-archive pass (no Haiku calls). Returns archived slugs."""
    from ..services.skill_distiller import garbage_collect_unused_skills
    archived = garbage_collect_unused_skills(grace_days=grace_days)
    return {"archived": archived, "count": len(archived)}

