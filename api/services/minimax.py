"""
MiniMax Direct API Service
Calls api.minimax.io (OpenAI-compatible).

Reuses DeepSeekService since MiniMax uses the same OpenAI-compatible API format.
"""
import logging
from typing import Optional

from .deepseek import DeepSeekService

logger = logging.getLogger(__name__)

# MiniMax uses the same OpenAI-compatible protocol as DeepSeek,
# so we simply alias DeepSeekService with a different default base_url.
MiniMaxService = DeepSeekService

# Singleton
_minimax_service: Optional[MiniMaxService] = None


def get_minimax_service() -> Optional[MiniMaxService]:
    return _minimax_service


def init_minimax_service(api_key: str, base_url: str = "https://api.minimax.chat/v1") -> MiniMaxService:
    global _minimax_service
    if _minimax_service:
        _minimax_service.update_api_key(api_key)
    else:
        _minimax_service = MiniMaxService(api_key, base_url)
    logger.info(f"MiniMax service initialized (base_url={base_url})")
    return _minimax_service
