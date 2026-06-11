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


def get_model_limits(model: str, **_kwargs) -> dict:
    """Get context-management limits for a model.

    Auto-derives limits from ``MODEL_REGISTRY.context_window``.
    Falls back to ``_DEFAULT_LIMITS`` for unknown models.
    """
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


# ---------------------------------------------------------------------------
# MODEL_REGISTRY -- unified registry for all Bedrock models
# ---------------------------------------------------------------------------
MODEL_REGISTRY: Dict[str, ModelInfo] = {
    # -----------------------------------------------------------------------
    # Anthropic Claude models  (api_format = "anthropic")
    # -----------------------------------------------------------------------
    "claude-opus-4-8": {
        "vendor": "bedrock",
        "bedrock_id": "us.anthropic.claude-opus-4-8",
        "provider": "anthropic",
        "display_name": "Claude Opus 4.8",
        "context_window": 1000000,
        "max_output": 64000,
        "supports_vision": True,
        "supports_thinking": False,
        "supports_tools": True,
        "api_format": "anthropic",
    },
    "claude-opus-4-7": {
        "vendor": "bedrock",
        "bedrock_id": "us.anthropic.claude-opus-4-7",
        "provider": "anthropic",
        "display_name": "Claude Opus 4.7",
        "context_window": 1000000,
        "max_output": 64000,
        "supports_vision": True,
        "supports_thinking": False,
        "supports_tools": True,
        "api_format": "anthropic",
    },
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
    },
    "claude-sonnet-4-6": {
        "vendor": "bedrock",
        "bedrock_id": "us.anthropic.claude-sonnet-4-6",
        "provider": "anthropic",
        "display_name": "Claude Sonnet 4.6",
        "context_window": 1000000,
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
    # Fable 5 is INFERENCE_PROFILE-only on Bedrock and has no `us.` profile —
    # it must be invoked via the `global.` profile ID (probed 2026-06-09).
    # Limits verified against the Bedrock Converse API: 1M context, 128K output.
    # Fable 5 uses ADAPTIVE thinking by default (cannot be disabled). Returns
    # reasoningContent for complex prompts, plain text for simple ones.
    "claude-fable-5": {
        "vendor": "bedrock",
        "bedrock_id": "global.anthropic.claude-fable-5",
        "provider": "anthropic",
        "display_name": "Claude Fable 5",
        "context_window": 1000000,
        "max_output": 128000,
        "supports_vision": True,
        "supports_thinking": True,  # Adaptive thinking (always on, auto-triggered)
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
    "minimax-m2.5": {
        "vendor": "bedrock",
        "bedrock_id": "minimax.minimax-m2.5",
        "provider": "minimax",
        "display_name": "MiniMax M2.5",
        "context_window": 204800,   # 200K
        "max_output": 131072,
        "supports_vision": False,
        "supports_thinking": True,
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
        "supports_thinking": True,
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
    "glm-5": {
        "vendor": "bedrock",
        "bedrock_id": "zai.glm-5",
        "provider": "zai",
        "display_name": "GLM 5",
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
_FLATTEN_TOOL_HISTORY_MODELS = {"glm-5"}

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


def get_api_format(model_name: str) -> str:
    """Return the api_format ('anthropic' or 'converse') for *model_name*.
    Defaults to 'anthropic' when the model is not registered."""
    info = MODEL_REGISTRY.get(model_name)
    return info.get("api_format", "anthropic") if info else "anthropic"


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
