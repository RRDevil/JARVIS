"""
Text sanitization and normalization utilities for natural spoken speech generation.
"""

from app.voice.normalizer import (
    normalize_text_for_speech,
    register_pronunciation,
    integer_to_words,
    year_to_words,
)


def clean_text_for_speech(text: str) -> str:
    """Sanitize and normalize text for clear, natural speech synthesis."""
    return normalize_text_for_speech(text)
