"""
Models Router for FastAPI
模型列表端点
"""
from fastapi import APIRouter
from typing import Any, Dict, List
import time
import logging

from ..services.bedrock import BEDROCK_MODEL_MAPPING

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/models")
async def list_models() -> Dict[str, Any]:
    """
    列出可用的 Bedrock 模型

    返回 OpenAI 兼容格式 + 扩展 Bedrock 信息。
    """
    now = int(time.time())
    models = []
    for anthropic_name, bedrock_id in BEDROCK_MODEL_MAPPING.items():
        family = "unknown"
        if "opus" in anthropic_name:
            family = "opus"
        elif "sonnet" in anthropic_name:
            family = "sonnet"
        elif "haiku" in anthropic_name:
            family = "haiku"

        models.append({
            "id": anthropic_name,
            "object": "model",
            "created": now,
            "bedrock_model_id": bedrock_id,
            "family": family,
            "provider": "anthropic",
        })

    return {
        "data": models,
        "object": "list",
        "total": len(models),
        "mapping": BEDROCK_MODEL_MAPPING,
    }
