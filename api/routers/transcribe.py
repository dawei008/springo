"""
WebSocket endpoint for real-time voice transcription.
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query

from ..services.transcribe import handle_transcription

router = APIRouter()


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
        await handle_transcription(ws, lang)
    except WebSocketDisconnect:
        pass
