"""
Persistent Voice Profile Management and Fallback Resolution.
Manages user-selectable voice profiles stored in the SQLite system_settings store.
"""

from datetime import datetime, timezone
import json
import logging
import os
import sqlite3
import threading
from typing import Dict, List, Optional, Tuple

from app.db.session import get_db_path, init_db
from app.voice.models import VoiceProfile, VoiceProfileCreate, VoiceProfileUpdate
from app.voice.tts.base import BaseTTSProvider
from app.voice.tts.registry import tts_registry

logger = logging.getLogger("jarvis.voice.profiles")

SETTING_KEY_PROFILES = "voice_profiles"
SETTING_KEY_ACTIVE_PROFILE = "active_voice_profile_id"

# Default baseline profiles
DEFAULT_PROFILES: List[Dict] = [
    {
        "id": "jarvis-default",
        "name": "J.A.R.V.I.S.",
        "provider_id": "sapi5",
        "voice_id": "HKEY_LOCAL_MACHINE\\SOFTWARE\\Microsoft\\Speech\\Voices\\Tokens\\TTS_MS_EN-US_DAVID_11.0",
        "language": "en-US",
        "rate": 180,
        "pitch": 1.0,
        "volume": 100,
        "is_favorite": True,
        "is_default": True,
        "is_fallback": True,
        "metadata": {"persona": "core_assistant"},
    },
    {
        "id": "assistant-zira",
        "name": "Windows Assistant (Zira)",
        "provider_id": "sapi5",
        "voice_id": "HKEY_LOCAL_MACHINE\\SOFTWARE\\Microsoft\\Speech\\Voices\\Tokens\\TTS_MS_EN-US_ZIRA_11.0",
        "language": "en-US",
        "rate": 180,
        "pitch": 1.0,
        "volume": 100,
        "is_favorite": False,
        "is_default": False,
        "is_fallback": False,
        "metadata": {},
    },
    {
        "id": "japanese-haruka",
        "name": "Japanese Voice (Haruka)",
        "provider_id": "sapi5",
        "voice_id": "HKEY_LOCAL_MACHINE\\SOFTWARE\\Microsoft\\Speech\\Voices\\Tokens\\TTS_MS_JA-JP_HARUKA_11.0",
        "language": "ja-JP",
        "rate": 180,
        "pitch": 1.0,
        "volume": 100,
        "is_favorite": False,
        "is_default": False,
        "is_fallback": False,
        "metadata": {},
    },
    {
        "id": "piper-lessac",
        "name": "Piper Neural (Lessac Medium)",
        "provider_id": "piper",
        "voice_id": "en_US-lessac-medium",
        "language": "en-US",
        "rate": 180,
        "pitch": 1.0,
        "volume": 100,
        "is_favorite": True,
        "is_default": False,
        "is_fallback": False,
        "metadata": {"engine": "onnx", "timbre": "clear_conversational"},
    },
    {
        "id": "teto-character",
        "name": "Kasane Teto (Character RVC)",
        "provider_id": "piper",
        "voice_id": "piper-teto-rvc",
        "language": "en-US",
        "rate": 180,
        "pitch": 1.0,
        "volume": 100,
        "is_favorite": True,
        "is_default": False,
        "is_fallback": False,
        "metadata": {
            "post_processor": "rvc",
            "rvc_model": "engines/voice_eval/models/TetoRVC/Kasane Teto.pth",
            "rvc_index": "engines/voice_eval/models/TetoRVC/added_IVF1367_Flat_nprobe_1_Kasane Teto_v2.index",
            "f0method": "pm",
            "f0up_key": 0,
        },
    },
    {
        "id": "custom-xtts",
        "name": "Neural Voice Clone (XTTS-v2)",
        "provider_id": "xtts-v2",
        "voice_id": "xtts-reference-sample",
        "language": "en-US",
        "rate": 180,
        "pitch": 1.0,
        "volume": 100,
        "is_favorite": False,
        "is_default": False,
        "is_fallback": False,
        "metadata": {"cloned": True},
    },
]


class VoiceProfileManager:
    """Coordinates persistence, CRUD operations, and fallback resolution for voice profiles."""

    def __init__(self):
        self._lock = threading.Lock()
        self._profiles: Dict[str, VoiceProfile] = {}
        self._active_profile_id: str = "jarvis-default"
        self._load_from_db()

    def _get_connection(self) -> sqlite3.Connection:
        init_db()
        db_path = get_db_path()
        return sqlite3.connect(str(db_path))

    def _load_from_db(self) -> None:
        """Load profiles and active selection from SQLite store; seeds defaults if unpopulated."""
        with self._lock:
            try:
                conn = self._get_connection()
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT value FROM system_settings WHERE key = ?",
                    (SETTING_KEY_PROFILES,),
                )
                row = cursor.fetchone()
                if row:
                    loaded_list = json.loads(row[0])
                    # Migration: Cleanse obsolete voicevox profiles
                    cleaned_list = [p for p in loaded_list if p.get("provider_id") != "voicevox" and p.get("id") != "character-voicevox"]
                    self._profiles = {p["id"]: VoiceProfile(**p) for p in cleaned_list}
                    
                    # Ensure piper-lessac baseline profile is present
                    if "piper-lessac" not in self._profiles:
                        piper_def = next((p for p in DEFAULT_PROFILES if p["id"] == "piper-lessac"), None)
                        if piper_def:
                            self._profiles["piper-lessac"] = VoiceProfile(**piper_def)

                    # Ensure teto-character profile is present
                    if "teto-character" not in self._profiles:
                        teto_def = next((p for p in DEFAULT_PROFILES if p["id"] == "teto-character"), None)
                        if teto_def:
                            self._profiles["teto-character"] = VoiceProfile(**teto_def)

                    # If entries were cleansed or updated, persist back to DB
                    if (
                        len(cleaned_list) != len(loaded_list)
                        or "piper-lessac" not in [p["id"] for p in loaded_list]
                        or "teto-character" not in [p["id"] for p in loaded_list]
                    ):
                        self._save_to_db(cursor)
                else:
                    # Seed defaults
                    self._profiles = {p["id"]: VoiceProfile(**p) for p in DEFAULT_PROFILES}
                    self._save_to_db(cursor)

                # Sync any on-disk discovered RVC character voice models
                if self._sync_discovered_rvc_profiles(cursor):
                    self._save_to_db(cursor)

                cursor.execute(
                    "SELECT value FROM system_settings WHERE key = ?",
                    (SETTING_KEY_ACTIVE_PROFILE,),
                )
                active_row = cursor.fetchone()
                if active_row and active_row[0] in self._profiles and active_row[0] != "character-voicevox":
                    self._active_profile_id = active_row[0]
                else:
                    self._active_profile_id = "jarvis-default"
                    self._save_to_db(cursor)

                conn.commit()
                conn.close()
            except Exception as exc:
                logger.warning(f"Error loading voice profiles from DB, using in-memory defaults: {exc}")
                self._profiles = {p["id"]: VoiceProfile(**p) for p in DEFAULT_PROFILES}
                self._active_profile_id = "jarvis-default"

    def _save_to_db(self, cursor: Optional[sqlite3.Cursor] = None) -> None:
        """Write current profiles and active profile ID to SQLite."""
        close_conn = False
        if cursor is None:
            conn = self._get_connection()
            cursor = conn.cursor()
            close_conn = True

        now = datetime.now(timezone.utc).isoformat()
        profiles_json = json.dumps([p.model_dump() for p in self._profiles.values()])

        cursor.execute(
            """
            INSERT INTO system_settings (key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
            """,
            (SETTING_KEY_PROFILES, profiles_json, now),
        )
        cursor.execute(
            """
            INSERT INTO system_settings (key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
            """,
            (SETTING_KEY_ACTIVE_PROFILE, self._active_profile_id, now),
        )

        if close_conn:
            cursor.connection.commit()
            cursor.connection.close()

    def rescan_rvc_models(self) -> bool:
        """Public trigger to re-synchronize profiles with on-disk RVC models."""
        return self._sync_discovered_rvc_profiles()

    def _sync_discovered_rvc_profiles(self, cursor: Optional[sqlite3.Cursor] = None) -> bool:
        """Dynamically synchronize profiles for all discovered on-disk RVC character models."""
        try:
            from app.voice.rvc_models import scan_rvc_models
            rvc_models = scan_rvc_models()
            updated = False
            for m in rvc_models:
                # Also link teto-character profile if this model is Kasane Teto
                if "teto" in m.id and "synth" not in m.id and "utau" not in m.id:
                    teto_prof = self._profiles.get("teto-character")
                    if teto_prof:
                        if teto_prof.name != m.name:
                            teto_prof.name = m.name
                            updated = True
                        if teto_prof.metadata.get("rvc_model") != m.model_path:
                            teto_prof.metadata["rvc_model"] = m.model_path
                            teto_prof.metadata["rvc_index"] = m.index_path
                            updated = True

                if m.id in self._profiles:
                    if self._profiles[m.id].name != m.name:
                        self._profiles[m.id].name = m.name
                        updated = True
                    if self._profiles[m.id].metadata.get("rvc_model") != m.model_path:
                        self._profiles[m.id].metadata["rvc_model"] = m.model_path
                        self._profiles[m.id].metadata["rvc_index"] = m.index_path
                        updated = True
                else:
                    self._profiles[m.id] = VoiceProfile(
                        id=m.id,
                        name=m.name,
                        provider_id="piper",
                        voice_id=f"piper-{m.id}",
                        language="en-US",
                        rate=180,
                        pitch=1.0,
                        volume=100,
                        is_favorite=True,
                        is_default=False,
                        is_fallback=False,
                        metadata={
                            "post_processor": "rvc",
                            "rvc_model": m.model_path,
                            "rvc_index": m.index_path,
                            "character_name": m.character_name,
                        },
                    )
                    updated = True

            # Deduplicate any duplicate profiles pointing to the identical model file
            seen_models = set()
            to_remove = []
            for pid, prof in self._profiles.items():
                m_path = prof.metadata.get("rvc_model")
                if m_path:
                    norm = os.path.normpath(m_path).lower()
                    if norm in seen_models:
                        to_remove.append(pid)
                    else:
                        seen_models.add(norm)
            for pid in to_remove:
                if pid != self._active_profile_id and not self._profiles[pid].is_fallback:
                    del self._profiles[pid]
                    updated = True

            # Ensure all RVC profile display names match the exact file name
            path_to_model = {os.path.normpath(m.model_path).lower(): m for m in rvc_models}
            for pid, prof in self._profiles.items():
                m_path = prof.metadata.get("rvc_model")
                if m_path:
                    norm = os.path.normpath(m_path).lower()
                    if norm in path_to_model:
                        exact = path_to_model[norm].name
                        if prof.name != exact:
                            prof.name = exact
                            updated = True
            return updated
        except Exception as exc:
            logger.warning(f"Error syncing discovered RVC profiles: {exc}")
            return False

    def list_profiles(self) -> List[VoiceProfile]:
        """List all registered voice profiles, dynamically reflecting any new on-disk RVC models."""
        with self._lock:
            if self._sync_discovered_rvc_profiles():
                self._save_to_db()
            return list(self._profiles.values())

    def get_profile(self, profile_id: str) -> Optional[VoiceProfile]:
        """Get profile by ID."""
        with self._lock:
            return self._profiles.get(profile_id)

    def get_active_profile(self) -> VoiceProfile:
        """Get the currently selected active profile."""
        with self._lock:
            return self._profiles.get(self._active_profile_id) or self.get_fallback_profile()

    def get_fallback_profile(self) -> VoiceProfile:
        """Get the designated universal fallback profile."""
        with self._lock:
            for p in self._profiles.values():
                if p.is_fallback:
                    return p
            # Default fallback if unset
            return next(iter(self._profiles.values()))

    def set_active_profile(self, profile_id: str) -> VoiceProfile:
        """Set the active voice profile."""
        with self._lock:
            if profile_id not in self._profiles:
                raise ValueError(f"Voice profile '{profile_id}' does not exist.")

            # Update is_default flags
            for pid, p in self._profiles.items():
                p.is_default = (pid == profile_id)

            self._active_profile_id = profile_id
            self._save_to_db()
            logger.info(f"Active voice profile set to '{profile_id}' ({self._profiles[profile_id].name})")
            return self._profiles[profile_id]

    def create_profile(self, create_data: VoiceProfileCreate) -> VoiceProfile:
        """Create and persist a new voice profile."""
        with self._lock:
            profile_id = create_data.id or f"profile-{int(datetime.now().timestamp() * 1000)}"
            if profile_id in self._profiles:
                raise ValueError(f"Profile ID '{profile_id}' already exists.")

            new_profile = VoiceProfile(
                id=profile_id,
                name=create_data.name,
                provider_id=create_data.provider_id,
                voice_id=create_data.voice_id,
                language=create_data.language,
                rate=create_data.rate,
                pitch=create_data.pitch,
                volume=create_data.volume,
                style=create_data.style,
                is_favorite=create_data.is_favorite,
                is_default=False,
                is_fallback=False,
                metadata=create_data.metadata,
            )
            self._profiles[profile_id] = new_profile
            self._save_to_db()
            logger.info(f"Created voice profile '{profile_id}' ({new_profile.name})")
            return new_profile

    def update_profile(self, profile_id: str, update_data: VoiceProfileUpdate) -> VoiceProfile:
        """Update fields of an existing voice profile."""
        with self._lock:
            profile = self._profiles.get(profile_id)
            if not profile:
                raise ValueError(f"Voice profile '{profile_id}' not found.")

            update_dict = update_data.model_dump(exclude_unset=True)
            for k, v in update_dict.items():
                if k == "is_default" and v is True:
                    # Clear other defaults
                    for p in self._profiles.values():
                        p.is_default = False
                    self._active_profile_id = profile_id
                setattr(profile, k, v)

            self._save_to_db()
            logger.info(f"Updated voice profile '{profile_id}'")
            return profile

    def delete_profile(self, profile_id: str) -> None:
        """Delete an existing voice profile. Protects fallback profile from deletion."""
        with self._lock:
            profile = self._profiles.get(profile_id)
            if not profile:
                raise ValueError(f"Voice profile '{profile_id}' not found.")

            if profile.is_fallback:
                raise ValueError(f"Cannot delete designated fallback voice profile '{profile_id}'.")

            del self._profiles[profile_id]

            # If active profile was deleted, switch back to fallback
            if self._active_profile_id == profile_id:
                fallback = self.get_fallback_profile()
                self._active_profile_id = fallback.id
                fallback.is_default = True

            self._save_to_db()
            logger.info(f"Deleted voice profile '{profile_id}'")

    def create_or_update_profile_for_voicepack(self, vp) -> VoiceProfile:
        """Create or update a voice profile mapped to an imported voicepack or RVC model."""
        with self._lock:
            if vp.id.startswith("rvc-") or vp.model_path.endswith(".pth"):
                profile_id = vp.id
                existing = self._profiles.get(profile_id)
                if existing:
                    existing.name = vp.name
                    existing.metadata["rvc_model"] = vp.model_path
                    existing.metadata["rvc_index"] = vp.config_path if vp.config_path.endswith(".index") else None
                    self._save_to_db()
                    return existing

                new_profile = VoiceProfile(
                    id=profile_id,
                    name=vp.name,
                    provider_id="piper",
                    voice_id=f"piper-{vp.id}",
                    language=vp.language,
                    rate=180,
                    pitch=1.0,
                    volume=100,
                    is_favorite=True,
                    is_default=False,
                    is_fallback=False,
                    metadata={
                        "imported": True,
                        "post_processor": "rvc",
                        "rvc_model": vp.model_path,
                        "rvc_index": vp.config_path if vp.config_path.endswith(".index") else None,
                        "character_name": vp.speakers[0] if vp.speakers else vp.name,
                    },
                )
                self._profiles[profile_id] = new_profile
                self._save_to_db()
                logger.info(f"Automatically registered RVC voice profile '{profile_id}' ({new_profile.name})")
                return new_profile

            profile_id = f"piper-{vp.id}"
            existing = self._profiles.get(profile_id)
            if existing:
                existing.name = f"Piper: {vp.name}"
                existing.voice_id = vp.id
                existing.language = vp.language
                self._save_to_db()
                return existing

            new_profile = VoiceProfile(
                id=profile_id,
                name=f"Piper: {vp.name}",
                provider_id="piper",
                voice_id=vp.id,
                language=vp.language,
                rate=180,
                pitch=1.0,
                volume=100,
                is_favorite=True,
                is_default=False,
                is_fallback=False,
                metadata={"imported": True, "voicepack_id": vp.id},
            )
            self._profiles[profile_id] = new_profile
            self._save_to_db()
            logger.info(f"Automatically registered voice profile '{profile_id}' for voicepack '{vp.id}'")
            return new_profile

    def remove_profiles_for_voicepack(self, voicepack_id: str) -> None:
        """Remove any voice profiles associated with a deleted voicepack."""
        with self._lock:
            to_remove = [
                pid for pid, p in self._profiles.items()
                if (p.provider_id == "piper" and p.voice_id == voicepack_id)
                or (p.metadata.get("voicepack_id") == voicepack_id)
            ]
            for pid in to_remove:
                if not self._profiles[pid].is_fallback:
                    del self._profiles[pid]
                    if self._active_profile_id == pid:
                        fallback = self.get_fallback_profile()
                        self._active_profile_id = fallback.id
                        fallback.is_default = True
            if to_remove:
                self._save_to_db()
                logger.info(f"Removed profiles associated with deleted voicepack '{voicepack_id}': {to_remove}")

    def resolve_profile_for_synthesis(
        self, profile_id: Optional[str] = None
    ) -> Tuple[VoiceProfile, BaseTTSProvider, bool, Optional[str]]:
        """
        Resolves the voice profile and underlying provider for a synthesis request.
        If the requested/active profile's provider is unavailable (e.g. offline engine or missing package),
        gracefully falls back to the designated SAPI profile with clear diagnostic reason.
        
        Returns:
            Tuple of (effective_profile, provider_instance, fallback_applied, fallback_reason)
        """
        target_profile = (
            self.get_profile(profile_id) if profile_id else self.get_active_profile()
        )
        if not target_profile:
            target_profile = self.get_fallback_profile()

        provider = tts_registry.get_provider(target_profile.provider_id)
        if provider and provider.is_available():
            return target_profile, provider, False, None

        # Provider is unavailable: apply clean fallback to SAPI fallback profile
        fallback_profile = self.get_fallback_profile()
        fallback_provider = tts_registry.get_default_provider()
        reason = (
            f"Voice profile '{target_profile.name}' uses provider '{target_profile.provider_id}', "
            f"which is currently unavailable or offline. Switched automatically to fallback profile '{fallback_profile.name}'."
        )
        logger.warning(reason)
        return fallback_profile, fallback_provider, True, reason


# Global singleton profile manager
profile_manager = VoiceProfileManager()

