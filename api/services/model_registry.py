"""
Unified Model Registry for Springo
Single source of truth for all supported Bedrock models (Claude + Chinese LLMs).
"""

from typing import Dict, List, Optional, TypedDict


class ModelInfo(TypedDict):
    bedrock_id: str
    provider: str
    display_name: str
    context_window: int
    max_output: int
    supports_vision: bool
    supports_thinking: bool
    supports_tools: bool
    api_format: str  # "anthropic" or "converse"


# ---------------------------------------------------------------------------
# Default context-management limits (used by bedrock.get_model_limits)
# ---------------------------------------------------------------------------
_DEFAULT_LIMITS = {
    "max_context_tokens": 200000,
    "compact_threshold": 120000,
    "warning_threshold": 160000,
    "target_after_summary": 40000,
    "max_output_tokens": 64000,
}

# Per-model overrides for context-management limits (keyed by short name).
# Models not listed here fall back to _DEFAULT_LIMITS.
_CONTEXT_LIMITS: Dict[str, dict] = {
    "claude-opus-4-6": {
        "max_context_tokens": 1000000,
        "compact_threshold": 600000,
        "warning_threshold": 800000,
        "target_after_summary": 200000,
        "max_output_tokens": 64000,
    },
}


def get_model_limits(model: str) -> dict:
    """Get context-management limits for a model. Returns defaults for unknown models."""
    return dict(_CONTEXT_LIMITS.get(model, _DEFAULT_LIMITS))


# ---------------------------------------------------------------------------
# MODEL_REGISTRY -- unified registry for all Bedrock models
# ---------------------------------------------------------------------------
MODEL_REGISTRY: Dict[str, ModelInfo] = {
    # -----------------------------------------------------------------------
    # Anthropic Claude models  (api_format = "anthropic")
    # -----------------------------------------------------------------------
    "claude-opus-4-6": {
        "bedrock_id": "us.anthropic.claude-opus-4-6-v1",
        "provider": "anthropic",
        "display_name": "Claude Opus 4.6",
        "context_window": 1000000,
        "max_output": 64000,
        "supports_vision": True,
        "supports_thinking": False,
        "supports_tools": True,
        "api_format": "anthropic",
    },
    "claude-sonnet-4-5-20250929": {
        "bedrock_id": "us.anthropic.claude-sonnet-4-5-20250929-v1:0",
        "provider": "anthropic",
        "display_name": "Claude Sonnet 4.5",
        "context_window": 200000,
        "max_output": 64000,
        "supports_vision": True,
        "supports_thinking": False,
        "supports_tools": True,
        "api_format": "anthropic",
    },
    "claude-haiku-4-5-20251001": {
        "bedrock_id": "us.anthropic.claude-haiku-4-5-20251001-v1:0",
        "provider": "anthropic",
        "display_name": "Claude Haiku 4.5",
        "context_window": 200000,
        "max_output": 64000,
        "supports_vision": True,
        "supports_thinking": False,
        "supports_tools": True,
        "api_format": "anthropic",
    },

    # -----------------------------------------------------------------------
    # DeepSeek  (api_format = "converse")
    # -----------------------------------------------------------------------
    "deepseek-v3.2": {
        "bedrock_id": "deepseek.v3.2",
        "provider": "deepseek",
        "display_name": "DeepSeek V3.2",
        "context_window": 128000,
        "max_output": 64000,
        "supports_vision": False,
        "supports_thinking": False,
        "supports_tools": True,
        "api_format": "converse",
    },

    # -----------------------------------------------------------------------
    # MiniMax  (api_format = "converse")
    # -----------------------------------------------------------------------
    "minimax-m2.1": {
        "bedrock_id": "minimax.minimax-m2.1",
        "provider": "minimax",
        "display_name": "MiniMax M2.1",
        "context_window": 200000,
        "max_output": 200000,
        "supports_vision": False,
        "supports_thinking": False,
        "supports_tools": True,
        "api_format": "converse",
    },

    # -----------------------------------------------------------------------
    # Moonshot AI (Kimi)  (api_format = "converse")
    # -----------------------------------------------------------------------
    "kimi-k2.5": {
        "bedrock_id": "moonshotai.kimi-k2.5",
        "provider": "moonshot",
        "display_name": "Kimi K2.5",
        "context_window": 256000,
        "max_output": 16384,
        "supports_vision": True,
        "supports_thinking": False,
        "supports_tools": True,
        "api_format": "converse",
    },

    # -----------------------------------------------------------------------
    # Qwen  (api_format = "converse")
    # -----------------------------------------------------------------------
    "qwen3-coder-480b": {
        "bedrock_id": "qwen.qwen3-coder-480b-a35b-v1:0",
        "provider": "qwen",
        "display_name": "Qwen3 Coder 480B",
        "context_window": 256000,
        "max_output": 16384,
        "supports_vision": False,
        "supports_thinking": False,
        "supports_tools": True,
        "api_format": "converse",
    },
    "qwen3-next-80b": {
        "bedrock_id": "qwen.qwen3-next-80b-a3b",
        "provider": "qwen",
        "display_name": "Qwen3 Next 80B",
        "context_window": 256000,
        "max_output": 16384,
        "supports_vision": False,
        "supports_thinking": False,
        "supports_tools": True,
        "api_format": "converse",
    },
    "qwen3-32b": {
        "bedrock_id": "qwen.qwen3-32b-v1:0",
        "provider": "qwen",
        "display_name": "Qwen3 32B",
        "context_window": 32000,
        "max_output": 16384,
        "supports_vision": False,
        "supports_thinking": False,
        "supports_tools": True,
        "api_format": "converse",
    },

    # -----------------------------------------------------------------------
    # Z.AI (GLM)  (api_format = "converse")
    # -----------------------------------------------------------------------
    "glm-4.7": {
        "bedrock_id": "zai.glm-4.7",
        "provider": "zai",
        "display_name": "GLM 4.7",
        "context_window": 200000,
        "max_output": 128000,
        "supports_vision": False,
        "supports_thinking": False,
        "supports_tools": True,
        "api_format": "converse",
    },
}

# Backward-compatible flat mapping: short_name -> bedrock_id
BEDROCK_MODEL_MAPPING: Dict[str, str] = {
    k: v["bedrock_id"] for k, v in MODEL_REGISTRY.items()
}


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def get_model_info(model_name: str) -> Optional[ModelInfo]:
    """Look up a model by short name. Returns None if not found."""
    return MODEL_REGISTRY.get(model_name)


def model_supports_tools(model_name: str) -> bool:
    """Check if a model supports tool use. Defaults to True for unknown models."""
    info = MODEL_REGISTRY.get(model_name)
    if info:
        return info.get("supports_tools", True)
    return True


def get_bedrock_id(model_name: str) -> str:
    """Return the Bedrock model ID for *model_name*.

    If the name is not in the registry the raw value is returned as-is,
    allowing callers to pass through arbitrary Bedrock IDs.
    """
    info = MODEL_REGISTRY.get(model_name)
    if info:
        return info["bedrock_id"]
    return model_name


def list_all_models() -> Dict[str, ModelInfo]:
    """Return the full registry (shallow copy)."""
    return dict(MODEL_REGISTRY)


def list_models_by_provider() -> Dict[str, List[Dict]]:
    """Return models grouped by provider, suitable for UI display."""
    grouped: Dict[str, List[Dict]] = {}
    for short_name, info in MODEL_REGISTRY.items():
        provider = info["provider"]
        if provider not in grouped:
            grouped[provider] = []
        grouped[provider].append({"name": short_name, **info})
    return grouped
