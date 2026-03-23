"""
Real-time voice transcription using local Whisper model (faster-whisper).
Receives PCM audio over WebSocket and returns transcript events.
Same interface as AWS Transcribe version — drop-in replacement.
"""

import asyncio
import io
import logging
import struct
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

import numpy as np
from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

# Singleton model instance — loaded once, shared across sessions
_model = None
_model_lock = asyncio.Lock()
_executor = ThreadPoolExecutor(max_workers=2)

# Audio config — must match frontend AudioWorklet output
SAMPLE_RATE = 16000
BYTES_PER_SAMPLE = 2  # 16-bit PCM

# Buffering config for real-time transcription
BUFFER_DURATION_SEC = 3.0  # Run inference every N seconds of audio
BUFFER_SIZE = int(SAMPLE_RATE * BUFFER_DURATION_SEC) * BYTES_PER_SAMPLE
# Keep trailing context for better continuity
OVERLAP_DURATION_SEC = 0.5
OVERLAP_SAMPLES = int(SAMPLE_RATE * OVERLAP_DURATION_SEC)


async def _get_model(model_size: str = "base"):
    """Lazy-load the Whisper model (thread-safe singleton)."""
    global _model
    if _model is not None:
        return _model

    async with _model_lock:
        if _model is not None:
            return _model

        logger.info(f"Loading Whisper model: {model_size} (first load may download ~150MB)")
        loop = asyncio.get_event_loop()

        def _load():
            from faster_whisper import WhisperModel
            # Use int8 on CPU for best speed; auto detects Apple Silicon
            return WhisperModel(model_size, device="cpu", compute_type="int8")

        _model = await loop.run_in_executor(_executor, _load)
        logger.info(f"Whisper model '{model_size}' loaded successfully")
        return _model


def _pcm_to_float32(pcm_bytes: bytes) -> np.ndarray:
    """Convert 16-bit PCM bytes to float32 numpy array normalized to [-1, 1]."""
    samples = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
    return samples


def _transcribe_buffer(model, audio: np.ndarray, language: Optional[str]) -> list:
    """Run whisper inference on an audio buffer. Returns list of segments."""
    kwargs = {
        "beam_size": 1,  # Greedy for speed in real-time
        "vad_filter": True,  # Skip silence
        "vad_parameters": {"min_silence_duration_ms": 500},
    }
    if language and language != "auto":
        kwargs["language"] = language

    segments, info = model.transcribe(audio, **kwargs)
    results = []
    for seg in segments:
        text = seg.text.strip()
        if text:
            results.append(text)
    return results


LANGUAGE_MAP = {
    "auto": None,
    "zh": "zh",
    "en": "en",
    "english": "en",
    "chinese": "zh",
    "zh-cn": "zh",
    "en-us": "en",
    "ja": "ja",
    "ko": "ko",
}


async def handle_transcription(ws: WebSocket, language: str = "auto",
                                model_size: str = "base"):
    """Handle a WebSocket transcription session using local Whisper."""
    lang = LANGUAGE_MAP.get(language.lower(), language if language != "auto" else None)
    logger.info(f"Local transcription started: lang={lang or 'auto'}, model={model_size}")

    model = await _get_model(model_size)
    loop = asyncio.get_event_loop()

    audio_buffer = bytearray()
    overlap_audio = np.array([], dtype=np.float32)
    last_inference_time = time.monotonic()

    try:
        while True:
            # Receive audio chunk from client
            try:
                data = await asyncio.wait_for(ws.receive_bytes(), timeout=30.0)
            except asyncio.TimeoutError:
                # No audio for 30s, send keepalive
                continue
            except WebSocketDisconnect:
                break

            audio_buffer.extend(data)

            # Check if we have enough audio for inference
            elapsed = time.monotonic() - last_inference_time
            if len(audio_buffer) < BUFFER_SIZE and elapsed < BUFFER_DURATION_SEC + 1.0:
                # Send partial indicator while buffering
                buffer_duration = len(audio_buffer) / (SAMPLE_RATE * BYTES_PER_SAMPLE)
                if len(audio_buffer) > SAMPLE_RATE * BYTES_PER_SAMPLE:  # > 1 sec
                    try:
                        await ws.send_json({
                            "type": "transcript",
                            "text": "...",
                            "is_partial": True,
                        })
                    except Exception:
                        break
                continue

            # Run inference on accumulated buffer
            pcm_bytes = bytes(audio_buffer)
            audio_buffer.clear()
            last_inference_time = time.monotonic()

            current_audio = _pcm_to_float32(pcm_bytes)

            # Prepend overlap from previous buffer for continuity
            if len(overlap_audio) > 0:
                full_audio = np.concatenate([overlap_audio, current_audio])
            else:
                full_audio = current_audio

            # Save trailing audio for next overlap
            if len(current_audio) > OVERLAP_SAMPLES:
                overlap_audio = current_audio[-OVERLAP_SAMPLES:]
            else:
                overlap_audio = current_audio

            # Run whisper in thread pool to avoid blocking event loop
            try:
                results = await loop.run_in_executor(
                    _executor,
                    _transcribe_buffer, model, full_audio, lang,
                )
            except Exception as e:
                logger.warning(f"Whisper inference error: {e}")
                continue

            # Send results
            if results:
                text = " ".join(results)
                try:
                    await ws.send_json({
                        "type": "transcript",
                        "text": text,
                        "is_partial": False,
                    })
                except Exception:
                    break
                logger.info(f"Transcribed: '{text[:80]}'")
            else:
                # Clear partial indicator
                try:
                    await ws.send_json({
                        "type": "transcript",
                        "text": "",
                        "is_partial": True,
                    })
                except Exception:
                    break

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"Local transcription error: {e}")
        try:
            await ws.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass

    # Process remaining buffer
    if len(audio_buffer) > SAMPLE_RATE * BYTES_PER_SAMPLE // 2:  # > 0.5s
        try:
            remaining = _pcm_to_float32(bytes(audio_buffer))
            if len(overlap_audio) > 0:
                remaining = np.concatenate([overlap_audio, remaining])
            results = await loop.run_in_executor(
                _executor,
                _transcribe_buffer, model, remaining, lang,
            )
            if results:
                text = " ".join(results)
                await ws.send_json({
                    "type": "transcript",
                    "text": text,
                    "is_partial": False,
                })
                logger.info(f"Final segment: '{text[:80]}'")
        except Exception:
            pass

    logger.info("Local transcription session ended")
