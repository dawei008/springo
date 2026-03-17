"""
Real-time voice transcription service using AWS Transcribe Streaming.
Receives PCM audio over WebSocket and returns transcript events.
"""

import asyncio
import logging

from amazon_transcribe.client import TranscribeStreamingClient
from amazon_transcribe.handlers import TranscriptResultStreamHandler
from amazon_transcribe.model import TranscriptEvent
from fastapi import WebSocket, WebSocketDisconnect

from ..config import settings

logger = logging.getLogger(__name__)

LANGUAGE_MAP = {
    "auto": "auto",
    "zh": "zh-CN",
    "en": "en-US",
    "english": "en-US",
    "chinese": "zh-CN",
    "zh-cn": "zh-CN",
    "en-us": "en-US",
    "ja": "ja-JP",
    "ko": "ko-KR",
}


async def handle_transcription(ws: WebSocket, language: str = "auto"):
    """Handle a single WebSocket transcription session."""
    lang_code = LANGUAGE_MAP.get(language.lower(), language)
    effective_lang = lang_code if lang_code != "auto" else "en-US"
    logger.info(f"Transcription session started: lang={effective_lang} (requested={language})")

    client_alive = True

    while client_alive:
        try:
            client_alive = await _run_transcribe_stream(ws, effective_lang)
            if client_alive:
                logger.info("AWS Transcribe stream ended, reconnecting...")
        except WebSocketDisconnect:
            logger.info("Client disconnected")
            break
        except Exception as e:
            logger.warning(f"Transcribe stream error ({type(e).__name__}): {e}")
            # Check if client is still connected before retrying
            try:
                await ws.send_json({"type": "error", "message": str(e)})
            except Exception:
                logger.info("Client gone during error notification, stopping")
                break

    logger.info("Transcription session ended")


async def _run_transcribe_stream(ws: WebSocket, lang_code: str) -> bool:
    """Run one AWS Transcribe streaming session.
    Returns True if client is still connected (should reconnect), False if client disconnected.
    """
    logger.info(f"Creating AWS Transcribe stream: region={settings.aws_region}, lang={lang_code}")
    client = TranscribeStreamingClient(region=settings.aws_region)

    stream = await client.start_stream_transcription(
        media_sample_rate_hz=16000,
        media_encoding="pcm",
        language_code=lang_code,
    )

    class _Handler(TranscriptResultStreamHandler):
        def __init__(self, output_stream, websocket: WebSocket):
            super().__init__(output_stream)
            self.ws = websocket

        async def handle_transcript_event(self, transcript_event: TranscriptEvent):
            results = transcript_event.transcript.results
            logger.info(f"Transcript event: {len(results)} results")
            for result in results:
                for alt in result.alternatives:
                    text = alt.transcript
                    is_partial = result.is_partial
                    logger.info(f"Transcript: partial={is_partial} text='{text[:80]}'")
                    msg = {
                        "type": "transcript",
                        "text": text,
                        "is_partial": is_partial,
                    }
                    if hasattr(result, "language_code") and result.language_code:
                        msg["language"] = result.language_code
                    try:
                        await self.ws.send_json(msg)
                    except Exception:
                        pass

    handler = _Handler(stream.output_stream, ws)
    client_disconnected = False
    logger.info("AWS Transcribe stream ready, receiving audio...")

    async def _send_audio():
        nonlocal client_disconnected
        chunk_count = 0
        try:
            while True:
                data = await ws.receive_bytes()
                chunk_count += 1

                # Normalize audio: boost signal to use more of the dynamic range
                import struct, math, array
                samples = struct.unpack(f'<{len(data)//2}h', data)
                peak = max(abs(s) for s in samples) if samples else 0

                if peak > 0:
                    # Target peak at ~60% of max to avoid clipping
                    target = 20000
                    gain = min(target / peak, 30.0)  # cap at 30x to avoid noise amplification
                    if gain > 1.5:
                        boosted = array.array('h', (max(-32768, min(32767, int(s * gain))) for s in samples))
                        data = boosted.tobytes()
                        if chunk_count <= 3 or chunk_count % 20 == 0:
                            new_peak = max(abs(s) for s in boosted)
                            logger.info(f"Audio chunk #{chunk_count}: peak={peak}→{new_peak} (gain={gain:.1f}x)")
                    elif chunk_count <= 3 or chunk_count % 20 == 0:
                        logger.info(f"Audio chunk #{chunk_count}: peak={peak} (no boost needed)")
                elif chunk_count <= 3 or chunk_count % 20 == 0:
                    logger.info(f"Audio chunk #{chunk_count}: silence")

                await stream.input_stream.send_audio_event(audio_chunk=data)
        except WebSocketDisconnect:
            client_disconnected = True
            logger.info(f"Client disconnected after {chunk_count} audio chunks")
        except Exception as e:
            if "disconnect" in str(e).lower():
                client_disconnected = True
            logger.warning(f"Audio send ended after {chunk_count} chunks: {type(e).__name__}: {e}")
        finally:
            await stream.input_stream.end_stream()

    # Run both tasks; when _send_audio ends (client disconnect or error),
    # handle_events will finish after processing remaining events
    await asyncio.gather(_send_audio(), handler.handle_events(), return_exceptions=True)

    return not client_disconnected
