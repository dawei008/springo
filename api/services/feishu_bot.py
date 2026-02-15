"""
Springo Feishu Bot Integration (Long-Connection Mode)
飞书机器人集成 — 使用 lark-oapi SDK 的 WebSocket 长连接模式
"""
import json
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

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

def _call_springo(session_id: str, user_text: str) -> str:
    """Call Springo messages-auto endpoint (SSE) and return the full response."""
    from ..config import settings
    payload = {
        "model": settings.default_chat_model,
        "messages": [{"role": "user", "content": user_text}],
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

        # Only handle text messages
        if msg_type != "text":
            _reply_text(message_id, "目前只支持文字消息")
            return

        # Extract text content
        content = json.loads(msg.content)
        user_text = content.get("text", "").strip()
        if not user_text:
            return

        logger.info(f"Feishu message from chat={chat_id}: {user_text[:80]}")

        # Offload heavy work to thread pool so the SDK can ACK immediately
        _executor.submit(_handle_message_async, chat_id, message_id, user_text)

    except Exception as e:
        logger.error(f"Feishu event handler error: {e}", exc_info=True)


def _handle_message_async(chat_id: str, message_id: str, user_text: str):
    """Process a Feishu message in a background thread (non-blocking)."""
    try:
        # Add emoji reaction to acknowledge receipt
        _add_reaction(message_id)

        # Map chat_id to session_id and call Springo
        session_id, _is_new = _get_session_id(chat_id)
        response_text = _call_springo(session_id, user_text)

        # Always set [Feishu] title AFTER _call_springo returns, because
        # _auto_save_session inside messages-auto overwrites the title
        # during the SSE stream.
        _set_session_title(session_id, user_text)

        # Reply in the same thread, split if too long
        remaining = response_text
        while remaining:
            chunk = remaining[:4000]
            remaining = remaining[4000:]
            _reply_text(message_id, chunk)

    except Exception as e:
        logger.error(f"Feishu async handler error: {e}", exc_info=True)


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
