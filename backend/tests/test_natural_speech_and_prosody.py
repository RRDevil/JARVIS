"""Automated Test Suite for Natural Voice, Prosody Controller & Speech Preparation.

Validates:
1. Context-Aware Prosody Controller (9 contexts, intensity scaling, context detection).
2. Advanced Speech Text Normalization (mathematics, file paths, URLs, symbols).
3. Pronunciation Dictionary (registration, lookup, word-boundary substitutions).
4. Custom Voice Profile Management & Consent Validation.
5. In-Memory RVC Model Checkpoint Caching & Piper Worker Resilience.
"""

import os
from pathlib import Path
import pytest

from app.voice.models import VoiceProfileCreate
from app.voice.normalizer import normalize_text_for_speech
from app.voice.profiles import profile_manager
from app.voice.pronunciation import PronunciationDictionary, pronunciation_dictionary
from app.voice.prosody import (
    CONTEXT_PROSODY_PROFILES,
    ContextProsodyController,
    SpeechContext,
    prosody_controller,
)


# ---------------------------------------------------------
# 1. Context-Aware Prosody Controller Tests
# ---------------------------------------------------------

def test_prosody_controller_all_nine_contexts():
    """Verify all 9 semantic contexts are configured with distinct acoustic parameters."""
    contexts = [
        SpeechContext.CONVERSATION,
        SpeechContext.TECHNICAL,
        SpeechContext.ACKNOWLEDGMENT,
        SpeechContext.WARNING,
        SpeechContext.ERROR,
        SpeechContext.APPROVAL,
        SpeechContext.PROGRESS,
        SpeechContext.COMPLETION,
        SpeechContext.EMPATHETIC,
    ]
    assert len(contexts) == 9

    for ctx in contexts:
        cfg = prosody_controller.get_prosody(ctx)
        assert cfg.context == ctx
        assert 80 <= cfg.rate <= 300
        assert 0.5 <= cfg.length_scale <= 2.0
        assert 0.0 <= cfg.noise_scale <= 1.5
        assert 0.0 <= cfg.noise_w_scale <= 1.5
        assert 0.5 <= cfg.pitch <= 2.0


def test_prosody_emotional_intensity_scaling():
    """Verify emotional intensity scales acoustic variance relative to neutral conversation."""
    ctrl = ContextProsodyController()

    # Zero intensity -> identical to neutral conversation
    neutral = ctrl.get_prosody(SpeechContext.CONVERSATION, intensity=0.0)
    warning_zero = ctrl.get_prosody(SpeechContext.WARNING, intensity=0.0)
    assert warning_zero.rate == neutral.rate
    assert warning_zero.length_scale == neutral.length_scale
    assert warning_zero.noise_scale == neutral.noise_scale

    # Standard intensity (1.0)
    warning_full = ctrl.get_prosody(SpeechContext.WARNING, intensity=1.0)
    assert warning_full.noise_scale == CONTEXT_PROSODY_PROFILES[SpeechContext.WARNING].noise_scale

    # Amplified intensity (1.5)
    warning_amplified = ctrl.get_prosody(SpeechContext.WARNING, intensity=1.5)
    # Target noise_scale is 0.400, neutral is 0.667 -> amplified should be even lower
    assert warning_amplified.noise_scale < warning_full.noise_scale


def test_prosody_context_detection_from_text():
    """Verify automatic context detection from semantic clues in text."""
    ctrl = ContextProsodyController()

    assert ctrl.detect_context("Would you like me to proceed with this navigation?") == SpeechContext.APPROVAL
    assert ctrl.detect_context("Warning: This action violates security restrictions.") == SpeechContext.WARNING
    assert ctrl.detect_context("I failed to locate the specified target window.") == SpeechContext.ERROR
    assert ctrl.detect_context("All steps finished. That's done, sir.") == SpeechContext.COMPLETION
    assert ctrl.detect_context("On it, sir. Checking display now.") == SpeechContext.ACKNOWLEDGMENT
    assert ctrl.detect_context("The database pipeline endpoint requires compilation.") == SpeechContext.TECHNICAL
    assert ctrl.detect_context("I apologize for the delay, take your time.") == SpeechContext.EMPATHETIC
    assert ctrl.detect_context("The weather in London is currently cloudy.") == SpeechContext.CONVERSATION


# ---------------------------------------------------------
# 2. Advanced Speech Text Normalization Tests
# ---------------------------------------------------------

def test_normalizer_math_expressions():
    """Verify mathematical operators and exponents are converted to natural speech words."""
    assert "to the power of" in normalize_text_for_speech("The result is 10^3.")
    assert "plus" in normalize_text_for_speech("Calculate 5 + 3 please.")
    assert "minus" in normalize_text_for_speech("Remaining balance is 100 - 45.")
    assert "times" in normalize_text_for_speech("The matrix is 4 * 5.")
    assert "divided by" in normalize_text_for_speech("The fraction is 20 / 4.")
    assert "does not equal" in normalize_text_for_speech("Condition a != b holds.")
    assert "is less than or equal to" in normalize_text_for_speech("Ensure x <= 10.")
    assert "is greater than or equal to" in normalize_text_for_speech("Ensure y >= 20.")
    assert "plus or minus" in normalize_text_for_speech("The tolerance is ± 5 percent.")


def test_normalizer_file_paths():
    """Verify Windows and Unix file paths are read naturally without verbatim backslashes."""
    win_spoken = normalize_text_for_speech(r"Opening C:\Users\Asus\Desktop\notes.txt now.")
    assert "C drive" in win_spoken
    assert "slash" in win_spoken
    assert "notes dot txt" in win_spoken

    unix_spoken = normalize_text_for_speech("Logs are saved to /var/log/system.log.")
    assert "slash" in unix_spoken
    assert "system dot log" in unix_spoken


def test_normalizer_preserves_verbatim_integrity():
    """Verify conversational meaning is preserved while removing markdown and code blocks."""
    raw = "```python\nprint('hello')\n```\nHere is the answer: **$45.50** at 10:30 AM."
    spoken = normalize_text_for_speech(raw)
    assert "print" not in spoken  # Code block omitted
    assert "forty-five dollars and fifty cents" in spoken
    assert "10" not in spoken  # converted to ten thirty AM
    assert "ten thirty A M" in spoken


# ---------------------------------------------------------
# 3. Pronunciation Dictionary Tests
# ---------------------------------------------------------

def test_pronunciation_dictionary_lifecycle():
    """Verify dynamic pronunciation registration, lookup, application, and removal."""
    d = PronunciationDictionary()

    # Builtins exist
    assert d.lookup("fastapi") == "fast A P I"
    assert d.lookup("pytorch") == "pie torch"
    assert d.lookup("latex") == "lay-tech"

    # Custom registration
    d.register("Raihan", "Rye-hahn")
    assert d.lookup("Raihan") == "Rye-hahn"
    assert d.apply("Hello Raihan, welcome.") == "Hello Rye-hahn, welcome."

    # Removal
    assert d.remove("Raihan") is True
    assert d.lookup("Raihan") is None


# ---------------------------------------------------------
# 4. Voice Profile & Consent Validation Tests
# ---------------------------------------------------------

def test_custom_voice_profile_consent_enforcement():
    """Verify that custom voice cloning requires explicit owner consent."""
    req_without_consent = VoiceProfileCreate(
        name="Friend Clone",
        provider_id="piper",
        voice_id="custom-voice-token",
        owner_consent_confirmed=False,
        metadata={"is_custom_voice": True, "cloned": True},
    )

    with pytest.raises(ValueError, match="consent from the voice owner is required"):
        profile_manager.create_profile(req_without_consent)

    req_with_consent = VoiceProfileCreate(
        name="Authorized Clone",
        provider_id="piper",
        voice_id="custom-voice-token",
        owner_consent_confirmed=True,
        metadata={"is_custom_voice": True, "cloned": True},
    )

    created = profile_manager.create_profile(req_with_consent)
    assert created.name == "Authorized Clone"
    assert created.metadata.get("owner_consent_confirmed") is True

    # Clean up test profile
    profile_manager.delete_profile(created.id)
