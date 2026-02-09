"""
Models Router for FastAPI
模型列表端点 — 从 MODEL_REGISTRY 返回模型能力信息
"""
from fastapi import APIRouter
from typing import Any, Dict, List
import time
import logging

from ..services.bedrock import MODEL_REGISTRY, BEDROCK_MODEL_MAPPING

logger = logging.getLogger(__name__)

router = APIRouter()

# Models shown in the settings UI (newest first)
_UI_MODELS = [
    "claude-opus-4-6",
    "claude-opus-4-5-20251101",
    "claude-sonnet-4-5-20250929",
    "claude-haiku-4-5-20251001",
]


@router.get("/models")
async def list_models() -> Dict[str, Any]:
    """
    列出可用的 Bedrock 模型（含能力参数）

    返回 OpenAI 兼容格式 + 扩展 Bedrock 信息和上下文能力。
    """
    now = int(time.time())
    models = []
    for model_id in _UI_MODELS:
        info = MODEL_REGISTRY.get(model_id)
        if not info:
            continue
        models.append({
            "id": model_id,
            "object": "model",
            "created": now,
            "bedrock_model_id": info["bedrock_id"],
            "display_name": info.get("display_name", model_id),
            "family": info.get("family", "unknown"),
            "provider": "anthropic",
            "recommended": info.get("recommended", False),
            "context": {
                "max_context_tokens": info["max_context_tokens"],
                "compact_threshold": info["compact_threshold"],
                "warning_threshold": info["warning_threshold"],
                "target_after_summary": info["target_after_summary"],
                "max_output_tokens": info["max_output_tokens"],
            },
        })

    return {
        "data": models,
        "object": "list",
        "total": len(models),
    }
