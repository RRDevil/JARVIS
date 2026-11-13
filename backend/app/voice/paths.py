"""
Centralized Model Directory Resolution and Asset Paths for J.A.R.V.I.S.

Allows large binary voice models (Faster-Whisper STT, Piper TTS ONNX, RVC weights)
to reside safely outside the Git repository so the codebase can be committed and
pushed to GitHub without triggering file size limits or Git LFS bandwidth restrictions.
"""

import os
import logging
from pathlib import Path
from typing import List, Optional, Union

logger = logging.getLogger("jarvis.voice.paths")

PROJECT_ROOT = Path(__file__).resolve().parents[3]
_RUNTIME_MODELS_DIR: Optional[Path] = None

UnionPath = Union[str, Path]


def get_base_models_dir() -> Path:
    """
    Resolve the active storage directory for large AI voice and speech models.
    
    Resolution Priority:
    1. Runtime override set via app settings or in-app configuration.
    2. Environment variable JARVIS_MODELS_DIR (from .env or OS environment).
    3. External sibling directory: <PROJECT_ROOT>/../JARVIS_MODELS (e.g. D:/Raihan/JARVIS_MODELS).
    4. User home directory: ~/.jarvis/models (e.g. C:/Users/<User>/.jarvis/models).
    5. Local repository fallback: <PROJECT_ROOT>/data/models.
    """
    global _RUNTIME_MODELS_DIR

    # 1. Runtime override
    if _RUNTIME_MODELS_DIR and _RUNTIME_MODELS_DIR.exists():
        return _RUNTIME_MODELS_DIR

    # 2. Environment variable
    env_dir = os.getenv("JARVIS_MODELS_DIR")
    if env_dir and env_dir.strip():
        p = Path(env_dir.strip()).resolve()
        p.mkdir(parents=True, exist_ok=True)
        return p

    # 3. External sibling directory
    sibling_external = (PROJECT_ROOT.parent / "JARVIS_MODELS").resolve()
    if sibling_external.exists():
        return sibling_external

    # 4. User profile directory if sibling not found
    home_dir = (Path.home() / ".jarvis" / "models").resolve()
    if home_dir.exists():
        return home_dir

    # Default to sibling external if created, or local fallback
    # If sibling_external doesn't exist yet, we check if local data/models has files
    local_data = (PROJECT_ROOT / "data" / "models").resolve()
    if local_data.exists() and any(local_data.iterdir()):
        return local_data

    # Otherwise prefer external sibling to avoid cluttering git
    sibling_external.mkdir(parents=True, exist_ok=True)
    return sibling_external


def set_runtime_models_dir(new_path: UnionPath) -> Path:
    """Set the active models directory at runtime."""
    global _RUNTIME_MODELS_DIR
    p = Path(new_path).resolve()
    p.mkdir(parents=True, exist_ok=True)
    _RUNTIME_MODELS_DIR = p
    logger.info(f"Switched active JARVIS models directory to: {p}")
    return p


def get_stt_models_dir() -> Path:
    """Directory for Faster-Whisper STT models (e.g. base.en, tiny.en, small.en)."""
    d = get_base_models_dir() / "stt"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_tts_piper_dir() -> Path:
    """Directory for Piper ONNX neural voices (.onnx + .json)."""
    d = get_base_models_dir() / "tts" / "piper"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_rvc_models_dir() -> Path:
    """Directory for RVC character voice models (.pth + .index)."""
    d = get_base_models_dir() / "voice" / "rvc"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_all_model_scan_dirs() -> List[Path]:
    """
    Return all valid directories to scan when discovering voicepacks and character weights.
    Includes active external directory, external 'Voices' folder, legacy folders, and local data.
    """
    candidates: List[Path] = []

    # 1. Active models directory
    active = get_base_models_dir()
    if active.exists() and active not in candidates:
        candidates.append(active)

    # 2. Sibling JARVIS_MODELS
    sibling = (PROJECT_ROOT.parent / "JARVIS_MODELS").resolve()
    if sibling.exists() and sibling not in candidates:
        candidates.append(sibling)

    # 3. External 'Voices' folder (e.g. D:/Raihan/Voices)
    voices_sibling = (PROJECT_ROOT.parent / "Voices").resolve()
    if voices_sibling.exists() and voices_sibling not in candidates:
        candidates.append(voices_sibling)

    # 4. User home ~/.jarvis/models
    home = (Path.home() / ".jarvis" / "models").resolve()
    if home.exists() and home not in candidates:
        candidates.append(home)

    # 5. Local repo data/models (legacy fallback)
    local_data = (PROJECT_ROOT / "data" / "models").resolve()
    if local_data.exists() and local_data not in candidates:
        candidates.append(local_data)

    # 6. Legacy voice_eval models
    legacy_eval = (PROJECT_ROOT / "engines" / "voice_eval" / "models").resolve()
    if legacy_eval.exists() and legacy_eval not in candidates:
        candidates.append(legacy_eval)

    return candidates
