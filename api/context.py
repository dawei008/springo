"""
Context Blueprint
Context management and summarization endpoints
"""

import json
import logging
from flask import Blueprint, request, Response

from context_manager import get_context_manager, get_stats as get_context_stats
from .shared import get_bedrock_client, json_response

logger = logging.getLogger(__name__)

context_bp = Blueprint('context', __name__)


@context_bp.route('/v1/context/stats', methods=['POST'])
def context_stats():
    """Get context statistics for messages"""
    try:
        data = request.get_json()
        messages = data.get('messages', [])
        stats = get_context_stats(messages)
        return json_response(stats)
    except Exception as e:
        logger.error(f"Context stats error: {e}")
        return json_response({"error": str(e)}, status=500)


@context_bp.route('/v1/context/summarize', methods=['POST'])
def context_summarize():
    """Summarize conversation context using Haiku model"""
    try:
        data = request.get_json()
        messages = data.get('messages', [])

        if not messages:
            return json_response({"error": "No messages provided"}, status=400)

        ctx_manager = get_context_manager()
        stats = ctx_manager.get_context_stats(messages)

        if not stats['needs_summarization']:
            return json_response({
                "summarized": False,
                "reason": "Context size is within limits",
                "stats": stats
            })

        bedrock_client = get_bedrock_client()
        summarized_messages = ctx_manager.summarize_context(messages, bedrock_client)

        new_stats = ctx_manager.get_context_stats(summarized_messages)

        return json_response({
            "summarized": True,
            "messages": summarized_messages,
            "original_stats": stats,
            "new_stats": new_stats,
            "tokens_saved": stats['total_tokens'] - new_stats['total_tokens']
        })

    except Exception as e:
        logger.error(f"Context summarize error: {e}")
        return json_response({"error": str(e)}, status=500)


@context_bp.route('/v1/context/auto-check', methods=['POST'])
def context_auto_check():
    """Auto-check and summarize if needed"""
    try:
        data = request.get_json()
        messages = data.get('messages', [])
        force = data.get('force', False)

        if not messages:
            return json_response({"error": "No messages provided"}, status=400)

        ctx_manager = get_context_manager()
        stats = ctx_manager.get_context_stats(messages)

        if not stats['needs_summarization'] and not force:
            return json_response({
                "action": "none",
                "reason": "Context size is within limits",
                "stats": stats
            })

        bedrock_client = get_bedrock_client()
        summarized_messages = ctx_manager.summarize_context(messages, bedrock_client)
        new_stats = ctx_manager.get_context_stats(summarized_messages)

        return json_response({
            "action": "summarized",
            "messages": summarized_messages,
            "original_stats": stats,
            "new_stats": new_stats,
            "tokens_saved": stats['total_tokens'] - new_stats['total_tokens']
        })

    except Exception as e:
        logger.error(f"Context auto-check error: {e}")
        return json_response({"error": str(e)}, status=500)
