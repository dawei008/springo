"""
Unified Model Registry for Springo
Single source of truth for all supported models (Bedrock + direct vendor APIs).
"""

from typing import Dict, List, Optional, TypedDict


class ModelInfo(TypedDict, total=False):
    vendor: str              # "bedrock" or "deepseek" (default "bedrock")
    vendor_model_id: str     # Model ID for the vendor's native API
    bedrock_id: str
    provider: str
    display_name: str
    context_window: int
    max_output: int
    supports_vision: bool
    supports_thinking: bool
    supports_tools: bool
    api_format: str  # "anthropic", "converse", or "openai"
    max_tools: int   # optional: limit tools sent to this model
    beta_features: List[str]  # optional: Bedrock anthropic_beta headers (e.g. "context-1m-2025-08-07")


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


def get_model_limits(model: str, extended_context: bool = True) -> dict:
    """Get context-management limits for a model.

    Priority:
    1. Explicit overrides in ``_CONTEXT_LIMITS`` (only when *extended_context* is True).
    2. Auto-derived from ``MODEL_REGISTRY.context_window / max_output``.
    3. ``_DEFAULT_LIMITS`` for unknown models.

    When *extended_context* is False and the model has an override in
    ``_CONTEXT_LIMITS``, the override is skipped and ``_DEFAULT_LIMITS``
    (200K) is returned instead.  This lets users opt out of the 1M beta.
    """
    if model in _CONTEXT_LIMITS:
        if extended_context:
            return dict(_CONTEXT_LIMITS[model])
        # extended_context disabled → fall back to standard 200K limits
        return dict(_DEFAULT_LIMITS)

    info = MODEL_REGISTRY.get(model)
    if info:
        ctx = info["context_window"]
        return {
            "max_context_tokens": ctx,
            "compact_threshold": int(ctx * 0.6),
            "warning_threshold": int(ctx * 0.8),
            "target_after_summary": int(ctx * 0.2),
            "max_output_tokens": info.get("max_output", 64000),
        }

    return dict(_DEFAULT_LIMITS)


def model_supports_extended_context(model: str) -> bool:
    """Return True if *model* supports the 1M extended context toggle."""
    return model in _CONTEXT_LIMITS


# ---------------------------------------------------------------------------
# MODEL_REGISTRY -- unified registry for all Bedrock models
# ---------------------------------------------------------------------------
MODEL_REGISTRY: Dict[str, ModelInfo] = {
    # -----------------------------------------------------------------------
    # Anthropic Claude models  (api_format = "anthropic")
    # -----------------------------------------------------------------------
    "claude-opus-4-6": {
        "vendor": "bedrock",
        "bedrock_id": "us.anthropic.claude-opus-4-6-v1",
        "provider": "anthropic",
        "display_name": "Claude Opus 4.6",
        "context_window": 1000000,
        "max_output": 64000,
        "supports_vision": True,
        "supports_thinking": False,
        "supports_tools": True,
        "api_format": "anthropic",
        "beta_features": ["context-1m-2025-08-07"],
    },
    "claude-sonnet-4-6": {
        "vendor": "bedrock",
        "bedrock_id": "us.anthropic.claude-sonnet-4-6",
        "provider": "anthropic",
        "display_name": "Claude Sonnet 4.6",
        "context_window": 200000,
        "max_output": 64000,
        "supports_vision": True,
        "supports_thinking": False,
        "supports_tools": True,
        "api_format": "anthropic",
    },
    "claude-sonnet-4-5-20250929": {
        "vendor": "bedrock",
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
        "vendor": "bedrock",
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
    # Bedrock context windows verified by probing the Converse API:
    #   input_tokens + maxTokens ≤ context_window (Bedrock-enforced)

    "deepseek-v3.2": {
        "vendor": "bedrock",
        "bedrock_id": "deepseek.v3.2",
        "provider": "deepseek",
        "display_name": "DeepSeek V3.2",
        "context_window": 163840,   # 160K (Bedrock-probed)
        "max_output": 65536,
        "supports_vision": False,
        "supports_thinking": False,
        "supports_tools": True,
        "api_format": "converse",
        "max_tools": 40,
    },

    # -----------------------------------------------------------------------
    # MiniMax  (api_format = "converse")
    # -----------------------------------------------------------------------
    "minimax-m2.1": {
        "vendor": "bedrock",
        "bedrock_id": "minimax.minimax-m2.1",
        "provider": "minimax",
        "display_name": "MiniMax M2.1",
        "context_window": 196608,   # 192K (Bedrock-probed)
        "max_output": 131072,
        "supports_vision": False,
        "supports_thinking": False,
        "supports_tools": True,
        "api_format": "converse",
        "max_tools": 40,
    },

    # -----------------------------------------------------------------------
    # Moonshot AI (Kimi)  (api_format = "converse")
    # -----------------------------------------------------------------------
    "kimi-k2.5": {
        "vendor": "bedrock",
        "bedrock_id": "moonshotai.kimi-k2.5",
        "provider": "moonshot",
        "display_name": "Kimi K2.5",
        "context_window": 262144,   # 256K (Bedrock-probed)
        "max_output": 131072,
        "supports_vision": True,
        "supports_thinking": False,
        "supports_tools": True,
        "api_format": "converse",
        "max_tools": 50,
    },

    # -----------------------------------------------------------------------
    # Qwen  (api_format = "converse")
    # -----------------------------------------------------------------------
    "qwen3-coder-480b": {
        "vendor": "bedrock",
        "bedrock_id": "qwen.qwen3-coder-480b-a35b-v1:0",
        "provider": "qwen",
        "display_name": "Qwen3 Coder 480B",
        "context_window": 131072,   # 128K on Bedrock (native 256K)
        "max_output": 65536,        # Qwen team recommended
        "supports_vision": False,
        "supports_thinking": False,
        "supports_tools": True,
        "api_format": "converse",
        "max_tools": 40,
    },
    # -----------------------------------------------------------------------
    # Z.AI (GLM)  (api_format = "converse")
    # -----------------------------------------------------------------------
    "glm-4.7": {
        "vendor": "bedrock",
        "bedrock_id": "zai.glm-4.7",
        "provider": "zai",
        "display_name": "GLM 4.7",
        "context_window": 202752,   # 198K (Bedrock-probed)
        "max_output": 131072,
        "supports_vision": False,
        "supports_thinking": False,
        "supports_tools": True,
        "api_format": "converse",
        "max_tools": 40,
    },

    # -----------------------------------------------------------------------
    # DeepSeek Direct API  (vendor = "deepseek", api_format = "openai")
    # -----------------------------------------------------------------------
    "deepseek-v3.2-direct": {
        "vendor": "deepseek",
        "vendor_model_id": "deepseek-chat",
        "bedrock_id": "",
        "provider": "deepseek-direct",
        "display_name": "DeepSeek V3.2 (Direct)",
        "context_window": 131072,
        "max_output": 8192,
        "supports_vision": False,
        "supports_thinking": False,
        "supports_tools": True,
        "api_format": "openai",
        "max_tools": 128,
    },

    # -----------------------------------------------------------------------
    # MiniMax Direct API  (vendor = "minimax", api_format = "openai")
    # -----------------------------------------------------------------------
    "minimax-m2.5-direct": {
        "vendor": "minimax",
        "vendor_model_id": "MiniMax-M2.5",
        "bedrock_id": "",
        "provider": "minimax-direct",
        "display_name": "MiniMax M2.5 (Direct)",
        "context_window": 204800,
        "max_output": 131072,
        "supports_vision": False,
        "supports_thinking": True,
        "supports_tools": True,
        "api_format": "openai",
        "max_tools": 128,
    },
}

# Models whose Bedrock Converse API integration cannot deserialize
# toolUse / toolResult content blocks in *message history*.  They support
# tool calls in the current turn, but past tool interactions must be
# flattened to plain text before re-sending.
_FLATTEN_TOOL_HISTORY_MODELS = {"glm-4.7"}

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


def model_needs_tool_flattening(model_name: str) -> bool:
    """Return True if past toolUse/toolResult blocks must be flattened to text."""
    return model_name in _FLATTEN_TOOL_HISTORY_MODELS


def get_max_tools(model_name: str) -> int:
    """Return the max number of tools a model can handle. 0 = unlimited."""
    info = MODEL_REGISTRY.get(model_name)
    if info:
        return info.get("max_tools", 0)
    return 0


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


def get_vendor(model_name: str) -> str:
    """Return the vendor for a model ('bedrock', 'deepseek', etc.).

    Defaults to 'bedrock' for unknown models.
    """
    info = MODEL_REGISTRY.get(model_name)
    if info:
        return info.get("vendor", "bedrock")
    return "bedrock"


def get_vendor_model_id(model_name: str) -> str:
    """Return the vendor-specific model ID.

    For Bedrock models this is the bedrock_id.
    For direct vendor models this is vendor_model_id.
    Falls back to the raw model_name if not found.
    """
    info = MODEL_REGISTRY.get(model_name)
    if info:
        vid = info.get("vendor_model_id")
        if vid:
            return vid
        return info.get("bedrock_id", model_name)
    return model_name
