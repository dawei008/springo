"""
Messages Blueprint
Core Claude API endpoints for messages
"""

import json
import uuid
import logging
from flask import Blueprint, request, Response, stream_with_context

from .shared import (
    get_bedrock_client,
    convert_anthropic_to_bedrock,
    handle_streaming_response,
    error_response,
    BEDROCK_MODEL_MAPPING,
)
from mcp_tools import execute_tool, get_tool_definitions

logger = logging.getLogger(__name__)

messages_bp = Blueprint('messages', __name__)


@messages_bp.route('/v1/messages', methods=['POST'])
def messages_api():
    """Claude Messages API - call Bedrock"""
    try:
        anthropic_request = request.get_json()
        logger.info(f"Messages API: model={anthropic_request.get('model')}, stream={anthropic_request.get('stream', False)}")

        model_id, bedrock_body = convert_anthropic_to_bedrock(anthropic_request)
        original_model = anthropic_request.get("model", "claude-3-5-sonnet-20241022")
        bedrock_client = get_bedrock_client()
        is_streaming = anthropic_request.get("stream", False)

        if is_streaming:
            return Response(
                stream_with_context(handle_streaming_response(
                    bedrock_client, model_id, bedrock_body, original_model
                )),
                mimetype='text/event-stream',
                headers={
                    'Cache-Control': 'no-cache',
                    'Connection': 'keep-alive',
                    'X-Accel-Buffering': 'no'
                }
            )
        else:
            response = bedrock_client.invoke_model(
                modelId=model_id,
                body=json.dumps(bedrock_body),
                contentType="application/json",
                accept="application/json"
            )

            bedrock_response = json.loads(response['body'].read())

            anthropic_response = {
                "id": f"msg_{uuid.uuid4().hex[:24]}",
                "type": "message",
                "role": "assistant",
                "content": bedrock_response.get("content", []),
                "model": original_model,
                "stop_reason": bedrock_response.get("stop_reason"),
                "stop_sequence": bedrock_response.get("stop_sequence"),
                "usage": {
                    "input_tokens": bedrock_response.get("usage", {}).get("input_tokens", 0),
                    "output_tokens": bedrock_response.get("usage", {}).get("output_tokens", 0),
                }
            }

            return Response(
                json.dumps(anthropic_response),
                mimetype='application/json',
                headers={'x-request-id': str(uuid.uuid4())}
            )

    except Exception as e:
        logger.error(f"Error: {e}")
        return error_response(e)


@messages_bp.route('/v1/messages-auto', methods=['POST'])
def messages_auto_api():
    """Auto tool execution API - eliminates frontend round-trips"""
    try:
        anthropic_request = request.get_json()
        logger.info(f"Messages Auto API: model={anthropic_request.get('model')}")

        model_id, bedrock_body = convert_anthropic_to_bedrock(anthropic_request)
        original_model = anthropic_request.get("model", "claude-3-5-sonnet-20241022")
        bedrock_client = get_bedrock_client()

        # Get compact model from request (default: Haiku 4.5 for cost efficiency)
        compact_model = anthropic_request.get("compact_model", "claude-haiku-4-5-20251001")

        def handle_auto_streaming():
            """Handle streaming with automatic tool execution

            Claude Code 风格：基于 context 窗口自动 compact，而非固定迭代次数
            """
            from context_manager import get_context_manager
            ctx_manager = get_context_manager()

            messages = list(bedrock_body.get("messages", []))
            # Claude Code 风格：基于 context 窗口，1000 仅作为安全上限
            max_iterations = 1000
            iteration = 0

            while iteration < max_iterations:
                iteration += 1

                # Context 检查和自动 compact
                if ctx_manager.should_summarize(messages):
                    logger.info(f"Context approaching limit, compacting with {compact_model}... (iteration {iteration})")
                    yield f"event: context_compact\ndata: {json.dumps({'type': 'context_compact', 'reason': 'approaching_limit', 'model': compact_model})}\n\n"
                    try:
                        messages = ctx_manager.summarize_messages(messages, model=compact_model)
                        logger.info(f"Context compacted, now {len(messages)} messages")
                    except Exception as e:
                        logger.warning(f"Context compact failed: {e}, continuing anyway")

                current_body = bedrock_body.copy()
                current_body["messages"] = messages

                response = bedrock_client.invoke_model_with_response_stream(
                    modelId=model_id,
                    body=json.dumps(current_body),
                    contentType="application/json",
                    accept="application/json"
                )

                message_id = f"msg_{uuid.uuid4().hex[:24]}"
                current_content = []
                tool_uses = []
                stop_reason = None

                for event in response.get("body", []):
                    chunk = json.loads(event.get("chunk", {}).get("bytes", b"{}"))
                    chunk_type = chunk.get("type")

                    if chunk_type == "message_start":
                        msg = chunk.get("message", {})
                        msg["model"] = original_model
                        yield f"event: message_start\ndata: {json.dumps({'type': 'message_start', 'message': msg})}\n\n"

                    elif chunk_type == "content_block_start":
                        content_block = chunk.get("content_block", {})
                        if content_block.get("type") == "tool_use":
                            tool_uses.append({
                                "index": chunk.get("index", 0),
                                "id": content_block.get("id", ""),
                                "name": content_block.get("name", ""),
                                "input": ""
                            })
                        yield f"event: content_block_start\ndata: {json.dumps({'type': 'content_block_start', 'index': chunk.get('index', 0), 'content_block': content_block})}\n\n"

                    elif chunk_type == "content_block_delta":
                        delta = chunk.get("delta", {})
                        if delta.get("type") == "input_json_delta" and tool_uses:
                            tool_uses[-1]["input"] += delta.get("partial_json", "")
                        yield f"event: content_block_delta\ndata: {json.dumps({'type': 'content_block_delta', 'index': chunk.get('index', 0), 'delta': delta})}\n\n"

                    elif chunk_type == "content_block_stop":
                        yield f"event: content_block_stop\ndata: {json.dumps({'type': 'content_block_stop', 'index': chunk.get('index', 0)})}\n\n"

                    elif chunk_type == "message_delta":
                        delta = chunk.get("delta", {})
                        stop_reason = delta.get("stop_reason")
                        yield f"event: message_delta\ndata: {json.dumps({'type': 'message_delta', 'delta': delta, 'usage': chunk.get('usage', {})})}\n\n"

                    elif chunk_type == "message_stop":
                        yield f"event: message_stop\ndata: {json.dumps({'type': 'message_stop'})}\n\n"

                # Check if we need to execute tools
                if stop_reason == "tool_use" and tool_uses:
                    # Build assistant message
                    assistant_content = []
                    for tu in tool_uses:
                        try:
                            input_json = json.loads(tu["input"]) if tu["input"] else {}
                        except:
                            input_json = {}
                        assistant_content.append({
                            "type": "tool_use",
                            "id": tu["id"],
                            "name": tu["name"],
                            "input": input_json
                        })

                    messages.append({"role": "assistant", "content": assistant_content})

                    # Execute tools and build results
                    tool_results = []
                    for tu in tool_uses:
                        try:
                            input_json = json.loads(tu["input"]) if tu["input"] else {}
                        except:
                            input_json = {}

                        result = execute_tool(tu["name"], input_json)
                        result_str = json.dumps(result)

                        # Truncate if too long
                        if len(result_str) > 50000:
                            result_str = result_str[:50000] + "...(truncated)"

                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": tu["id"],
                            "content": result_str
                        })

                        # Send tool result event
                        yield f"event: tool_result\ndata: {json.dumps({'type': 'tool_result', 'tool_use_id': tu['id'], 'tool_name': tu['name'], 'result': result})}\n\n"

                    # Send tool execution complete event
                    yield f"event: tool_execution_complete\ndata: {json.dumps({'type': 'tool_execution_complete', 'count': len(tool_results)})}\n\n"

                    messages.append({"role": "user", "content": tool_results})
                else:
                    # No more tools to execute
                    break

        return Response(
            stream_with_context(handle_auto_streaming()),
            mimetype='text/event-stream',
            headers={
                'Cache-Control': 'no-cache',
                'Connection': 'keep-alive',
                'X-Accel-Buffering': 'no'
            }
        )

    except Exception as e:
        logger.error(f"Auto API Error: {e}")
        return error_response(e)


@messages_bp.route('/v1/models', methods=['GET'])
def list_models():
    """List available models"""
    import time
    models = [
        {"id": model, "created": int(time.time()), "object": "model"}
        for model in BEDROCK_MODEL_MAPPING.keys()
    ]
    return Response(json.dumps({"data": models, "object": "list"}), mimetype='application/json')
