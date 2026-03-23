"""
WebSocket endpoint for real-time voice transcription.
Dispatches to AWS Transcribe or local Whisper based on config.
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from fastapi.responses import JSONResponse

from ..config import settings

router = APIRouter()


@router.get("/transcribe/status")
async def transcribe_status():
    """Get current ASR engine configuration."""
    return JSONResponse({
        "engine": settings.asr_engine,
        "model_size": settings.whisper_model_size if settings.asr_engine == "local" else None,
    })


@router.websocket("/transcribe")
async def transcribe_ws(ws: WebSocket, lang: str = Query("auto")):
    """
    WebSocket endpoint for streaming audio transcription.

    Connect: ws://localhost:8081/v1/transcribe?lang=zh
    Send: binary PCM frames (16-bit signed, 16kHz, mono)
    Receive: JSON { type: "transcript", text: "...", is_partial: bool }
    """
    await ws.accept()
    try:
        if settings.asr_engine == "local":
            from ..services.transcribe_local import handle_transcription
            await handle_transcription(ws, lang, model_size=settings.whisper_model_size)
        else:
            from ..services.transcribe import handle_transcription
            await handle_transcription(ws, lang)
    except WebSocketDisconnect:
        pass
