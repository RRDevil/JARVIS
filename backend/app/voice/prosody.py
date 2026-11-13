"""J.A.R.V.I.S. Context-Aware Prosody Controller.

Translates conversational context and semantic intent into acoustic prosody parameters
(speaking rate, length scale, phoneme variation, pitch, and energy) with graceful
provider degradation.
"""

from enum import Enum
import logging
import re
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field

logger = logging.getLogger("jarvis.voice.prosody")


class SpeechContext(str, Enum):
    """Categorical semantic delivery styles for J.A.R.V.I.S."""
    CONVERSATION = "conversation"      # Calm, natural, balanced conversational cadence
    TECHNICAL = "technical"            # Clear, measured, articulate technical explanations
    ACKNOWLEDGMENT = "acknowledgment"  # Relaxed, natural, concise task acknowledgments
    WARNING = "warning"                # Firm, serious, appropriately urgent alerts
    ERROR = "error"                    # Calm, informative, steady error notifications
    APPROVAL = "approval"              # Brief, neutral, crisp permission inquiries
    PROGRESS = "progress"              # Confident, concise, reassuring task progress
    COMPLETION = "completion"          # Natural, conclusive, satisfied confirmations
    EMPATHETIC = "empathetic"          # Warm, restrained, attentive assistance


class ContextProsodyConfig(BaseModel):
    """Acoustic prosody settings for neural and standard TTS engines."""
    context: SpeechContext
    rate: int = Field(default=180, ge=80, le=300, description="Speaking rate in words per minute.")
    length_scale: float = Field(default=1.0, ge=0.5, le=2.0, description="Phoneme duration length scale.")
    noise_scale: float = Field(default=0.667, ge=0.0, le=1.5, description="Acoustic variation / expressive noise scale.")
    noise_w_scale: float = Field(default=0.8, ge=0.0, le=1.5, description="Phoneme timing rhythm scale.")
    pitch: float = Field(default=1.0, ge=0.5, le=2.0, description="Pitch multiplier (where supported).")
    volume: int = Field(default=100, ge=0, le=100, description="Volume percentage.")
    description: str = Field(default="Balanced cinematic delivery", description="Human-readable description.")


# Baseline Acoustic Parameter Profiles for Balanced Cinematic Delivery
CONTEXT_PROSODY_PROFILES: Dict[SpeechContext, ContextProsodyConfig] = {
    SpeechContext.CONVERSATION: ContextProsodyConfig(
        context=SpeechContext.CONVERSATION,
        rate=180,
        length_scale=1.0,
        noise_scale=0.667,
        noise_w_scale=0.800,
        pitch=1.0,
        volume=100,
        description="Calm, natural, balanced cinematic delivery.",
    ),
    SpeechContext.TECHNICAL: ContextProsodyConfig(
        context=SpeechContext.TECHNICAL,
        rate=170,
        length_scale=1.08,
        noise_scale=0.500,
        noise_w_scale=0.700,
        pitch=0.98,
        volume=100,
        description="Clear, measured, articulate technical explanation.",
    ),
    SpeechContext.ACKNOWLEDGMENT: ContextProsodyConfig(
        context=SpeechContext.ACKNOWLEDGMENT,
        rate=190,
        length_scale=0.95,
        noise_scale=0.600,
        noise_w_scale=0.750,
        pitch=1.0,
        volume=95,
        description="Relaxed, natural, concise acknowledgment.",
    ),
    SpeechContext.WARNING: ContextProsodyConfig(
        context=SpeechContext.WARNING,
        rate=175,
        length_scale=1.05,
        noise_scale=0.400,
        noise_w_scale=0.900,
        pitch=0.95,
        volume=100,
        description="Firm, serious, urgent warning.",
    ),
    SpeechContext.ERROR: ContextProsodyConfig(
        context=SpeechContext.ERROR,
        rate=175,
        length_scale=1.02,
        noise_scale=0.500,
        noise_w_scale=0.700,
        pitch=0.97,
        volume=100,
        description="Calm, informative, steady recovery update.",
    ),
    SpeechContext.APPROVAL: ContextProsodyConfig(
        context=SpeechContext.APPROVAL,
        rate=185,
        length_scale=0.98,
        noise_scale=0.550,
        noise_w_scale=0.750,
        pitch=1.0,
        volume=100,
        description="Brief, neutral, crisp approval inquiry.",
    ),
    SpeechContext.PROGRESS: ContextProsodyConfig(
        context=SpeechContext.PROGRESS,
        rate=190,
        length_scale=0.94,
        noise_scale=0.600,
        noise_w_scale=0.750,
        pitch=1.0,
        volume=92,
        description="Confident, concise, reassuring task progress.",
    ),
    SpeechContext.COMPLETION: ContextProsodyConfig(
        context=SpeechContext.COMPLETION,
        rate=180,
        length_scale=1.0,
        noise_scale=0.667,
        noise_w_scale=0.800,
        pitch=1.0,
        volume=100,
        description="Natural, conclusive, satisfied task completion.",
    ),
    SpeechContext.EMPATHETIC: ContextProsodyConfig(
        context=SpeechContext.EMPATHETIC,
        rate=170,
        length_scale=1.10,
        noise_scale=0.750,
        noise_w_scale=0.850,
        pitch=1.02,
        volume=95,
        description="Warm, restrained, attentive assistance.",
    ),
}


class ContextProsodyController:
    """Provider-independent prosody controller that computes acoustic parameters."""

    def __init__(self, default_intensity: float = 1.0):
        self.default_intensity = max(0.0, min(2.0, default_intensity))

    def detect_context(self, text: str, default: SpeechContext = SpeechContext.CONVERSATION) -> SpeechContext:
        """Infer suitable semantic speech context from text clues if not explicitly supplied."""
        if not text:
            return default

        lower = text.lower().strip()

        # 1. Warnings and security alerts (highest priority)
        if "warning:" in lower or "caution:" in lower or "security restriction" in lower or "violates security" in lower:
            return SpeechContext.WARNING

        # 2. Errors and failures
        if "failed to" in lower or "error:" in lower or "unable to" in lower or "could not" in lower or "exception" in lower:
            return SpeechContext.ERROR

        # 3. Approval inquiries & decisions
        if any(term in lower for term in ("authorize", "authorization", "permission", "would you like me to proceed", "approval required", "confirm")):
            return SpeechContext.APPROVAL

        # 4. Task completion
        if any(term in lower for term in ("task complete", "completed successfully", "all steps finished", "operation complete", "all set, sir")):
            return SpeechContext.COMPLETION

        # 5. Immediate acknowledgments
        if lower.startswith(("on it", "right away", "working on it", "checking that", "understood")):
            return SpeechContext.ACKNOWLEDGMENT

        # 6. Task Progress (in-flight action narration)
        if lower.startswith(("navigating", "scanning", "processing", "loading", "searching", "clicking", "reading", "fetching")) or "in progress" in lower:
            return SpeechContext.PROGRESS

        # 7. Technical content (mentions of code, databases, API, memory, architecture)
        if any(term in lower for term in ("function", "algorithm", "database", "pipeline", "architecture", "endpoint", "protocol", "compilation", "server", "latency", "fastapi", "pytorch", "models", "cache", "requests")):
            return SpeechContext.TECHNICAL

        # 8. Empathetic phrases
        if any(term in lower for term in ("i understand", "i apologize", "no worries", "take your time", "glad to help")):
            return SpeechContext.EMPATHETIC

        return default

    def get_prosody(
        self,
        context: SpeechContext = SpeechContext.CONVERSATION,
        intensity: Optional[float] = None,
        base_rate: Optional[int] = None,
        base_pitch: Optional[float] = None,
    ) -> ContextProsodyConfig:
        """
        Derive final acoustic parameters for a given context and intensity level.
        Intensity scales the delta between neutral conversation and the target profile.
        """
        target = CONTEXT_PROSODY_PROFILES.get(context, CONTEXT_PROSODY_PROFILES[SpeechContext.CONVERSATION])
        neutral = CONTEXT_PROSODY_PROFILES[SpeechContext.CONVERSATION]

        scale = self.default_intensity if intensity is None else max(0.0, min(2.0, intensity))

        # Blend parameters between neutral and target according to emotional intensity
        effective_rate = round(neutral.rate + (target.rate - neutral.rate) * scale)
        if base_rate is not None:
            rate_delta = effective_rate - neutral.rate
            effective_rate = max(80, min(300, base_rate + rate_delta))

        effective_length = round(neutral.length_scale + (target.length_scale - neutral.length_scale) * scale, 3)
        effective_noise = round(neutral.noise_scale + (target.noise_scale - neutral.noise_scale) * scale, 3)
        effective_noise_w = round(neutral.noise_w_scale + (target.noise_w_scale - neutral.noise_w_scale) * scale, 3)

        effective_pitch = round(neutral.pitch + (target.pitch - neutral.pitch) * scale, 3)
        if base_pitch is not None:
            pitch_delta = effective_pitch - neutral.pitch
            effective_pitch = max(0.5, min(2.0, round(base_pitch + pitch_delta, 3)))

        effective_volume = round(neutral.volume + (target.volume - neutral.volume) * scale)

        return ContextProsodyConfig(
            context=context,
            rate=effective_rate,
            length_scale=effective_length,
            noise_scale=effective_noise,
            noise_w_scale=effective_noise_w,
            pitch=effective_pitch,
            volume=effective_volume,
            description=target.description,
        )


# Global singleton instance
prosody_controller = ContextProsodyController()
