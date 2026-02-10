"""
Models Router for FastAPI
模型列表端点 — 从 MODEL_REGISTRY 返回模型能力信息
"""
from fastapi import APIRouter
from typing import Any, Dict, List
import time
import logging

from ..services.model_registry import (
    MODEL_REGISTRY,
    BEDROCK_MODEL_MAPPING,
    list_models_by_provider,
    get_model_limits,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# Default model IDs (used when frontend has no stored preference)
DEFAULT_MODEL = "claude-opus-4-6"
DEFAULT_COMPACT_MODEL = "claude-haiku-4-5-20251001"


@router.get("/models")
async def list_models() -> Dict[str, Any]:
    """
    列出可用的 Bedrock 模型（含能力参数）

    返回 OpenAI 兼容格式 + 扩展 Bedrock 信息和上下文能力。
    Also includes models grouped by provider and default model hints.
    """
    now = int(time.time())

    # Build flat list of all models (backward compatible with existing frontend)
    models = []
    for model_id, info in MODEL_REGISTRY.items():
        limits = get_model_limits(model_id)
        models.append({
            "id": model_id,
            "object": "model",
            "created": now,
            "bedrock_model_id": info["bedrock_id"],
            "display_name": info.get("display_name", model_id),
            "provider": info.get("provider", "unknown"),
            "context_window": info.get("context_window", 200000),
            "max_output": info.get("max_output", 64000),
            "supports_vision": info.get("supports_vision", False),
            "supports_thinking": info.get("supports_thinking", False),
            "api_format": info.get("api_format", "anthropic"),
            "context": {
                "max_context_tokens": limits["max_context_tokens"],
                "compact_threshold": limits["compact_threshold"],
                "warning_threshold": limits["warning_threshold"],
                "target_after_summary": limits["target_after_summary"],
                "max_output_tokens": limits["max_output_tokens"],
            },
        })

    # Build provider-grouped dict for UI optgroup rendering
    grouped: Dict[str, List[Dict]] = {}
    for m in models:
        provider = m["provider"]
        if provider not in grouped:
            grouped[provider] = []
        grouped[provider].append(m)

    return {
        "data": models,
        "models": grouped,
        "default_model": DEFAULT_MODEL,
        "default_compact_model": DEFAULT_COMPACT_MODEL,
        "object": "list",
        "total": len(models),
    }
