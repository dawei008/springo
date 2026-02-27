"""
Springo Feishu Bot Integration (Long-Connection Mode)
飞书机器人集成 — 使用 lark-oapi SDK 的 WebSocket 长连接模式

Supported message types:
  - text: plain text messages
  - image: image messages (downloaded from Feishu, sent to Claude as base64)
  - post: rich text messages (text + images extracted and sent as multimodal)
  - file: file messages (image files supported, others returned as text note)
"""
import base64
import json
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, List, Optional, Union

import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level state
# ---------------------------------------------------------------------------
_feishu_thread: Optional[threading.Thread] = None
_lark_client = None  # lark.Client for API calls
_session_map: dict[str, str] = {}  # chat_id -> session_id
_session_file: Optional[Path] = None
_base_url: str = ""
_active: bool = False  # guards event handler; False = ignore events from stale threads
_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="feishu-worker")
_processed_msgs: dict[str, float] = {}  # message_id -> timestamp, for dedup
_DEDUP_TTL = 300  # ignore duplicate events within 5 minutes


# ---------------------------------------------------------------------------
# Session persistence helpers
# ---------------------------------------------------------------------------

def _load_sessions() -> dict[str, str]:
    if _session_file and _session_file.exists():
        try:
            return json.loads(_session_file.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_sessions():
    if _session_file:
        _session_file.parent.mkdir(parents=True, exist_ok=True)
        _session_file.write_text(json.dumps(_session_map, ensure_ascii=False, indent=2), encoding="utf-8")


def _get_session_id(chat_id: str) -> tuple[str, bool]:
    """Get or create a Springo session_id for a Feishu chat_id.

    Returns (session_id, is_new) so caller can set the title on first use.
    """
    is_new = chat_id not in _session_map
    if is_new:
        import uuid
        _session_map[chat_id] = str(uuid.uuid4())
        _save_sessions()
    return _session_map[chat_id], is_new


# ---------------------------------------------------------------------------
# Feishu message helpers
# ---------------------------------------------------------------------------

def _reply_text(message_id: str, text: str):
    """Reply to a Feishu message with text content."""
    from lark_oapi.api.im.v1 import (
        ReplyMessageRequest,
        ReplyMessageRequestBody,
    )

    body = ReplyMessageRequestBody.builder() \
        .msg_type("text") \
        .content(json.dumps({"text": text})) \
        .build()

    req = ReplyMessageRequest.builder() \
        .message_id(message_id) \
        .request_body(body) \
        .build()

    resp = _lark_client.im.v1.message.reply(req)
    if not resp.success():
        logger.warning(f"Feishu reply failed: {resp.code} {resp.msg}")
    return resp


def _add_reaction(message_id: str, emoji_type: str = "OnIt"):
    """Add an emoji reaction to a Feishu message."""
    from lark_oapi.api.im.v1 import (
        CreateMessageReactionRequest,
        CreateMessageReactionRequestBody,
        Emoji,
    )

    body = CreateMessageReactionRequestBody.builder() \
        .reaction_type(Emoji.builder().emoji_type(emoji_type).build()) \
        .build()

    req = CreateMessageReactionRequest.builder() \
        .message_id(message_id) \
        .request_body(body) \
        .build()

    resp = _lark_client.im.v1.message_reaction.create(req)
    if not resp.success():
        logger.warning(f"Feishu reaction failed: {resp.code} {resp.msg}")
    return resp


def _download_image(message_id: str, image_key: str) -> Optional[tuple[bytes, str]]:
    """Download an image from Feishu using the message resource API.

    Returns (image_bytes, media_type) or None on failure.
    """
    from lark_oapi.api.im.v1 import GetMessageResourceRequest

    req = GetMessageResourceRequest.builder() \
        .message_id(message_id) \
        .file_key(image_key) \
        .type("image") \
        .build()

    resp = _lark_client.im.v1.message_resource.get(req)
    if not resp.success():
        logger.warning(f"Feishu image download failed: {resp.code} {resp.msg}")
        return None

    image_bytes = resp.file.read() if resp.file else None
    if not image_bytes:
        logger.warning("Feishu image download returned empty data")
        return None

    # Detect media type from magic bytes
    media_type = "image/png"
    if image_bytes[:3] == b'\xff\xd8\xff':
        media_type = "image/jpeg"
    elif image_bytes[:4] == b'\x89PNG':
        media_type = "image/png"
    elif image_bytes[:4] == b'GIF8':
        media_type = "image/gif"
    elif image_bytes[:4] == b'RIFF' and image_bytes[8:12] == b'WEBP':
        media_type = "image/webp"

    logger.info(f"Downloaded Feishu image: {len(image_bytes)} bytes, {media_type}")
    return image_bytes, media_type


def _parse_post_content(message_id: str, content: dict) -> tuple[str, List[dict]]:
    """Parse Feishu rich text (post) message into text + image blocks.

    Returns (combined_text, list_of_claude_content_blocks).
    """
    blocks: List[dict] = []
    text_parts: List[str] = []

    # Post content structure: {"title": "...", "content": [[{tag, ...}, ...], ...]}
    title = content.get("title", "")
    if title:
        text_parts.append(title)

    for paragraph in content.get("content", []):
        para_text = ""
        for element in paragraph:
            tag = element.get("tag", "")
            if tag == "text":
                para_text += element.get("text", "")
            elif tag == "a":
                href = element.get("href", "")
                link_text = element.get("text", href)
                para_text += f"{link_text} ({href})" if link_text != href else href
            elif tag == "at":
                para_text += element.get("user_name", "@someone")
            elif tag == "img":
                image_key = element.get("image_key", "")
                if image_key:
                    result = _download_image(message_id, image_key)
                    if result:
                        img_bytes, media_type = result
                        b64 = base64.b64encode(img_bytes).decode("utf-8")
                        blocks.append({
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": b64,
                            },
                        })
        if para_text.strip():
            text_parts.append(para_text.strip())

    combined_text = "\n".join(text_parts).strip()
    return combined_text, blocks


def _build_content_blocks(
    text: str = "",
    image_data: Optional[tuple[bytes, str]] = None,
    extra_blocks: Optional[List[dict]] = None,
) -> Union[str, List[dict]]:
    """Build Claude-compatible content (string or content block list).

    If only text, returns a simple string.
    If images are involved, returns a list of content blocks.
    """
    has_images = image_data is not None or (extra_blocks and len(extra_blocks) > 0)

    if not has_images:
        return text

    blocks: List[dict] = []

    # Add text block first if present
    if text:
        blocks.append({"type": "text", "text": text})

    # Add single image if provided
    if image_data:
        img_bytes, media_type = image_data
        b64 = base64.b64encode(img_bytes).decode("utf-8")
        blocks.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": media_type,
                "data": b64,
            },
        })

    # Add extra blocks (from rich text parsing)
    if extra_blocks:
        blocks.extend(extra_blocks)

    return blocks if blocks else text


def _set_session_title(session_id: str, user_text: str):
    """Set Springo session title with [Feishu] prefix."""
    title = f"[Feishu] {user_text[:60]}"
    try:
        with httpx.Client(timeout=5.0) as client:
            client.patch(
                f"{_base_url}/v1/sessions/{session_id}",
                json={"metadata": {"title": title}},
            )
    except Exception as e:
        logger.debug(f"Failed to set Feishu session title: {e}")


# ---------------------------------------------------------------------------
# Core: call Springo /v1/messages-auto and collect response
# ---------------------------------------------------------------------------

def _call_springo(session_id: str, content: Union[str, list]) -> str:
    """Call Springo messages-auto endpoint (SSE) and return the full response.

    Args:
        session_id: Springo session ID
        content: Either a plain text string or a list of Claude content blocks
                 (text + image blocks for multimodal messages)
    """
    from ..config import settings
    payload = {
        "model": settings.default_chat_model,
        "messages": [{"role": "user", "content": content}],
        "stream": True,
        "max_tokens": 16384,
    }
    headers = {
        "Content-Type": "application/json",
        "X-Session-Id": session_id,
    }

    full_text = ""
    try:
        with httpx.Client(timeout=httpx.Timeout(300.0, connect=10.0)) as client:
            with client.stream("POST", f"{_base_url}/v1/messages-auto", json=payload, headers=headers) as resp:
                for line in resp.iter_lines():
                    if not line.startswith("data: "):
                        continue
                    data_str = line[6:]
                    if data_str == "[DONE]":
                        break
                    try:
                        evt = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue

                    evt_type = evt.get("type", "")

                    # Each new text block resets full_text so we only keep
                    # the FINAL iteration's text (skip intermediate "thinking" text
                    # from tool-use cycles).
                    if evt_type == "content_block_start":
                        block = evt.get("content_block", {})
                        if block.get("type") == "text":
                            full_text = ""

                    # content_block_delta carries text fragments
                    elif evt_type == "content_block_delta":
                        delta = evt.get("delta", {})
                        if delta.get("type") == "text_delta":
                            full_text += delta.get("text", "")

    except Exception as e:
        logger.error(f"Feishu→Springo call error: {e}")
        full_text = full_text or f"[Error communicating with Springo: {e}]"

    return full_text.strip() or "[No response]"


# ---------------------------------------------------------------------------
# Dedup helper
# ---------------------------------------------------------------------------

def _is_duplicate(message_id: str) -> bool:
    """Check if this message was already processed (dedup against server retries)."""
    now = time.time()
    # Clean expired entries
    expired = [k for k, t in _processed_msgs.items() if now - t > _DEDUP_TTL]
    for k in expired:
        del _processed_msgs[k]
    if message_id in _processed_msgs:
        return True
    _processed_msgs[message_id] = now
    return False


# ---------------------------------------------------------------------------
# Feishu event handler
# ---------------------------------------------------------------------------

def _on_message(data):
    """Handle incoming Feishu P2ImMessageReceiveV1 event.

    Supported message types: text, image, post (rich text), file (image files).
    Returns immediately to let the SDK send the ACK frame.
    Heavy work (call Springo, reply) runs in a thread pool.
    """
    if not _active:
        return  # stale thread — ignore

    try:
        msg = data.event.message
        chat_id = msg.chat_id
        message_id = msg.message_id
        msg_type = msg.message_type

        # Dedup: skip if we already processed this message
        if _is_duplicate(message_id):
            logger.debug(f"Feishu dedup: skipping duplicate event for message_id={message_id}")
            return

        content = json.loads(msg.content)

        if msg_type == "text":
            user_text = content.get("text", "").strip()
            if not user_text:
                return
            logger.info(f"Feishu text from chat={chat_id}: {user_text[:80]}")
            _executor.submit(_handle_message_async, chat_id, message_id, user_text, user_text)

        elif msg_type == "image":
            image_key = content.get("image_key", "")
            if not image_key:
                return
            logger.info(f"Feishu image from chat={chat_id}: image_key={image_key}")
            _executor.submit(_handle_image_message, chat_id, message_id, image_key)

        elif msg_type == "post":
            # Rich text: extract text + inline images
            # Post content is locale-keyed: {"zh_cn": {...}, "en_us": {...}}
            post_body = None
            for lang_key in ("zh_cn", "en_us", "ja_jp"):
                if lang_key in content:
                    post_body = content[lang_key]
                    break
            if not post_body:
                # Fallback: try first key
                post_body = next(iter(content.values()), None) if content else None
            if not post_body:
                return
            logger.info(f"Feishu post from chat={chat_id}: title={post_body.get('title', '')[:40]}")
            _executor.submit(_handle_post_message, chat_id, message_id, post_body)

        elif msg_type == "file":
            file_name = content.get("file_name", "")
            file_key = content.get("file_key", "")
            # Support image files sent as file type
            lower_name = file_name.lower()
            if file_key and any(lower_name.endswith(ext) for ext in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp")):
                logger.info(f"Feishu image file from chat={chat_id}: {file_name}")
                _executor.submit(_handle_image_message, chat_id, message_id, file_key)
            else:
                _reply_text(message_id, f"暂不支持该文件类型：{file_name}\n目前支持：文字、图片、富文本消息")

        else:
            _reply_text(message_id, "暂不支持该消息类型，目前支持：文字、图片、富文本消息")

    except Exception as e:
        logger.error(f"Feishu event handler error: {e}", exc_info=True)


def _handle_message_async(
    chat_id: str,
    message_id: str,
    content: Union[str, list],
    title_text: str,
):
    """Process a Feishu message in a background thread (non-blocking).

    Args:
        chat_id: Feishu chat ID
        message_id: Feishu message ID (for reply)
        content: Claude-compatible content (string or list of content blocks)
        title_text: Plain text for session title
    """
    try:
        # Add emoji reaction to acknowledge receipt
        _add_reaction(message_id)

        # Map chat_id to session_id and call Springo
        session_id, _ = _get_session_id(chat_id)
        response_text = _call_springo(session_id, content)

        # Always set [Feishu] title AFTER _call_springo returns, because
        # _auto_save_session inside messages-auto overwrites the title
        # during the SSE stream.
        _set_session_title(session_id, title_text)

        # Reply in the same thread, split if too long
        remaining = response_text
        while remaining:
            chunk = remaining[:4000]
            remaining = remaining[4000:]
            _reply_text(message_id, chunk)

    except Exception as e:
        logger.error(f"Feishu async handler error: {e}", exc_info=True)


def _handle_image_message(chat_id: str, message_id: str, image_key: str):
    """Handle an image message: download from Feishu, send to Claude as base64."""
    try:
        _add_reaction(message_id)

        result = _download_image(message_id, image_key)
        if not result:
            _reply_text(message_id, "图片下载失败，请重试")
            return

        content = _build_content_blocks(
            text="请描述/分析这张图片。",
            image_data=result,
        )
        title_text = "[图片]"

        session_id, _ = _get_session_id(chat_id)
        response_text = _call_springo(session_id, content)
        _set_session_title(session_id, title_text)

        remaining = response_text
        while remaining:
            chunk = remaining[:4000]
            remaining = remaining[4000:]
            _reply_text(message_id, chunk)

    except Exception as e:
        logger.error(f"Feishu image handler error: {e}", exc_info=True)


def _handle_post_message(chat_id: str, message_id: str, post_body: dict):
    """Handle a rich text (post) message: extract text + inline images."""
    try:
        _add_reaction(message_id)

        combined_text, image_blocks = _parse_post_content(message_id, post_body)
        if not combined_text and not image_blocks:
            return

        content = _build_content_blocks(
            text=combined_text,
            extra_blocks=image_blocks,
        )
        title_text = combined_text[:60] if combined_text else "[富文本]"

        session_id, _ = _get_session_id(chat_id)
        response_text = _call_springo(session_id, content)
        _set_session_title(session_id, title_text)

        remaining = response_text
        while remaining:
            chunk = remaining[:4000]
            remaining = remaining[4000:]
            _reply_text(message_id, chunk)

    except Exception as e:
        logger.error(f"Feishu post handler error: {e}", exc_info=True)


# ---------------------------------------------------------------------------
# WebSocket client thread
# ---------------------------------------------------------------------------

def _run_ws_client(app_id: str, app_secret: str):
    """Run the lark-oapi WebSocket client (blocking). Called in a daemon thread."""
    import asyncio
    import lark_oapi as lark
    import lark_oapi.ws.client as _ws_mod

    # The SDK captures the event loop at module import time (line 26 of
    # lark_oapi/ws/client.py).  When imported from uvicorn's main thread,
    # that loop is already running → run_until_complete() raises
    # "This event loop is already running".
    # Fix: create a fresh loop for this thread and patch the module ref.
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    _ws_mod.loop = loop

    handler = lark.EventDispatcherHandler.builder("", "") \
        .register_p2_im_message_receive_v1(_on_message) \
        .build()

    cli = lark.ws.Client(
        app_id=app_id,
        app_secret=app_secret,
        event_handler=handler,
        log_level=lark.LogLevel.INFO,
    )
    logger.info("Feishu bot WebSocket client starting...")
    try:
        cli.start()  # blocks
    finally:
        loop.close()


# ---------------------------------------------------------------------------
# Config reader (shared by init & restart)
# ---------------------------------------------------------------------------

def _read_feishu_config() -> dict:
    """Read merged Feishu config from settings + config.json."""
    import os
    from ..config import settings

    app_id = settings.feishu_app_id
    app_secret = settings.feishu_app_secret
    enabled = settings.feishu_enabled

    try:
        cfg_file = os.path.expanduser("~/.springo/config.json")
        if os.path.exists(cfg_file):
            with open(cfg_file, 'r') as f:
                cfg = json.load(f)
            feishu_cfg = cfg.get("integrations", {}).get("feishu", {})
            if feishu_cfg:
                if feishu_cfg.get("enabled") is not None:
                    enabled = feishu_cfg["enabled"]
                if feishu_cfg.get("app_id"):
                    app_id = feishu_cfg["app_id"]
                if feishu_cfg.get("app_secret"):
                    app_secret = feishu_cfg["app_secret"]
    except Exception as e:
        logger.debug(f"Could not read Feishu config from config.json: {e}")

    return {"enabled": enabled, "app_id": app_id, "app_secret": app_secret}


# ---------------------------------------------------------------------------
# Public API: init / shutdown / restart
# ---------------------------------------------------------------------------

async def init_feishu_bot():
    """Initialize and start the Feishu bot if configured."""
    import lark_oapi as lark
    from ..config import settings

    conf = _read_feishu_config()
    enabled = conf["enabled"]
    app_id = conf["app_id"]
    app_secret = conf["app_secret"]

    if not enabled:
        logger.debug("Feishu bot disabled (feishu_enabled=false)")
        return

    if not app_id or not app_secret:
        raise ValueError("Feishu app_id and app_secret are required when feishu_enabled=true")

    # Set module-level state
    global _lark_client, _session_map, _session_file, _base_url, _feishu_thread, _active

    _base_url = f"http://127.0.0.1:{settings.port}"
    _session_file = settings.springo_config_path / "feishu_sessions.json"
    _session_map = _load_sessions()

    # Create lark client for API calls (reply/patch/create messages)
    _lark_client = lark.Client.builder() \
        .app_id(app_id) \
        .app_secret(app_secret) \
        .log_level(lark.LogLevel.INFO) \
        .build()

    _active = True

    # Start WebSocket long-connection in a daemon thread
    _feishu_thread = threading.Thread(
        target=_run_ws_client,
        args=(app_id, app_secret),
        daemon=True,
        name="feishu-ws",
    )
    _feishu_thread.start()
    logger.info("Feishu bot connected (WebSocket)")


def shutdown_feishu_bot():
    """Shutdown Feishu bot. Deactivates event handler; daemon thread exits with process."""
    global _feishu_thread, _active
    _active = False
    _processed_msgs.clear()
    if _feishu_thread and _feishu_thread.is_alive():
        logger.info("Feishu bot shutting down (daemon thread will exit with process)")
    _feishu_thread = None


async def restart_feishu_bot():
    """Restart Feishu bot with current config. Called after config save."""
    shutdown_feishu_bot()
    conf = _read_feishu_config()
    if conf["enabled"] and conf["app_id"] and conf["app_secret"]:
        await init_feishu_bot()
        return True
    logger.info("Feishu bot not restarted (disabled or missing credentials)")
    return False
