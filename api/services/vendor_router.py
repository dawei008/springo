"""
Vendor Router — dispatches model calls to the correct backend service
(BedrockService or DeepSeekService) based on the model's vendor field.
"""
import logging
from typing import AsyncGenerator, Dict, Any, Optional

from .model_registry import get_vendor, get_vendor_model_id, get_model_info

logger = logging.getLogger(__name__)


class VendorRouter:
    """Routes API calls to the correct vendor service."""

    def __init__(self):
        self.bedrock = None      # BedrockService
        self.deepseek = None     # DeepSeekService
        self.minimax = None      # MiniMaxService (OpenAI-compatible, reuses DeepSeekService)

    def initialize(self, bedrock, deepseek=None, minimax=None):
        self.bedrock = bedrock
        self.deepseek = deepseek
        self.minimax = minimax
        vendors = ["bedrock"]
        if deepseek:
            vendors.append("deepseek")
        if minimax:
            vendors.append("minimax")
        logger.info(f"VendorRouter initialized with vendors: {vendors}")

    def get_service(self, model: str):
        """Return the service for a model based on its vendor.

        Raises ValueError if the vendor service is required but not configured
        (i.e. the model has no bedrock_id fallback).
        """
        vendor = get_vendor(model)

        if vendor == "deepseek":
            if self.deepseek:
                return self.deepseek
            # Check if this model has a bedrock_id fallback
            info = get_model_info(model)
            has_bedrock_fallback = info and info.get("bedrock_id")
            if has_bedrock_fallback:
                logger.warning(f"Model {model} vendor=deepseek not available, falling back to Bedrock")
                return self.bedrock
            raise ValueError(
                "DeepSeek API key not configured. "
                "Go to Settings → DeepSeek to enter your API key."
            )

        if vendor == "minimax":
            if self.minimax:
                return self.minimax
            info = get_model_info(model)
            has_bedrock_fallback = info and info.get("bedrock_id")
            if has_bedrock_fallback:
                logger.warning(f"Model {model} vendor=minimax not available, falling back to Bedrock")
                return self.bedrock
            raise ValueError(
                "MiniMax API key not configured. "
                "Go to Settings → MiniMax to enter your API key."
            )

        return self.bedrock

    def has_vendor(self, vendor: str) -> bool:
        """Check if a vendor service is available."""
        if vendor == "bedrock":
            return self.bedrock is not None
        if vendor == "deepseek":
            return self.deepseek is not None
        if vendor == "minimax":
            return self.minimax is not None
        return False

    # ------------------------------------------------------------------
    # Delegated methods — match BedrockService interface
    # ------------------------------------------------------------------

    def convert_request_to_bedrock(
        self,
        request: Dict[str, Any],
        include_tools: bool = True,
        tools: list = None,
        working_dir: str = None,
    ) -> tuple[str, Dict[str, Any]]:
        """Convert request using the appropriate service."""
        model = request.get("model", "")
        service = self.get_service(model)
        if hasattr(service, 'convert_request'):
            return service.convert_request(request, include_tools=include_tools, tools=tools, working_dir=working_dir)
        return service.convert_request_to_bedrock(request, include_tools=include_tools, tools=tools, working_dir=working_dir)

    def get_bedrock_model_id(self, model: str) -> str:
        service = self.get_service(model)
        return service.get_bedrock_model_id(model)

    def get_api_format(self, model: str) -> str:
        service = self.get_service(model)
        return service.get_api_format(model)

    async def invoke_model(
        self,
        model_id: str,
        body: Dict[str, Any],
        max_retries: int = 3,
        api_format: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Route to the correct service for non-streaming invocation."""
        # Determine vendor from the original model name stored in body
        original_model = body.get("_original_model", "")
        service = self.get_service(original_model) if original_model else self.bedrock
        return await service.invoke_model(model_id, body, max_retries=max_retries, api_format=api_format)

    async def invoke_model_stream(
        self,
        model_id: str,
        body: Dict[str, Any],
        original_model: str,
        max_retries: int = 3,
        api_format: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """Route to the correct service for streaming invocation."""
        service = self.get_service(original_model)
        async for event in service.invoke_model_stream(model_id, body, original_model, max_retries=max_retries, api_format=api_format):
            yield event

    async def invoke_model_stream_text(
        self,
        model_id: str,
        body: Dict[str, Any],
        max_retries: int = 3,
        api_format: Optional[str] = None,
    ) -> AsyncGenerator[dict, None]:
        """Route to the correct service for text streaming (agent teams)."""
        original_model = body.get("_original_model", "")
        service = self.get_service(original_model) if original_model else self.bedrock
        async for event in service.invoke_model_stream_text(model_id, body, max_retries=max_retries, api_format=api_format):
            yield event


# Singleton
_vendor_router: Optional[VendorRouter] = None


def get_vendor_router() -> VendorRouter:
    """Get the vendor router singleton."""
    global _vendor_router
    if _vendor_router is None:
        _vendor_router = VendorRouter()
    return _vendor_router


def init_vendor_router(bedrock, deepseek=None, minimax=None) -> VendorRouter:
    """Initialize the vendor router with services."""
    router = get_vendor_router()
    router.initialize(bedrock, deepseek, minimax)
    return router
