"""
utils/transcriber.py
Handles audio transcription via OpenAI Whisper.
The model is loaded once at import time (lazy singleton) to avoid
re-loading the large checkpoint on every request.
"""

import logging
import whisper

log = logging.getLogger(__name__)

# ── Singleton model loader ─────────────────────────────────────────────────
_whisper_model = None
_MODEL_SIZE = "base"   # options: tiny, base, small, medium, large


def _get_model():
    global _whisper_model
    if _whisper_model is None:
        log.info("Loading Whisper '%s' model…", _MODEL_SIZE)
        try:
            _whisper_model = whisper.load_model(_MODEL_SIZE)
            log.info("Whisper model loaded successfully.")
        except Exception as exc:
            log.error("Failed to load Whisper model: %s", exc)
            raise RuntimeError(
                f"Whisper model '{_MODEL_SIZE}' could not be loaded. "
                f"Check your installation and VRAM availability. Details: {exc}"
            ) from exc
    return _whisper_model