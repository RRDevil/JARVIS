"""
Voicepack Management and Asset Discovery Subsystem.
Coordinates discovery, validation, safe importing, and removal of pretrained voice models.
"""

from io import BytesIO
import json
import logging
import os
from pathlib import Path
import shutil
from typing import Dict, List, Optional, Tuple, Union
import zipfile

from app.voice.models import VoicepackInfo, VoicepackStatus
from app.voice.paths import get_tts_piper_dir, get_all_model_scan_dirs

logger = logging.getLogger("jarvis.voice.voicepacks")

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_VOICEPACKS_DIR = get_tts_piper_dir()
LEGACY_MODELS_DIR = (PROJECT_ROOT / "engines" / "voice_eval" / "models").resolve()

# Strict security whitelist for file extensions inside imported voicepacks and character models
ALLOWED_EXTENSIONS = {".onnx", ".json", ".txt", ".md", ".pth", ".index"}
MAX_ARCHIVE_SIZE_BYTES = 500 * 1024 * 1024  # 500 MB limit


class VoicepackManager:
    """Manages on-disk voice assets, safe import extraction, and metadata indexing."""

    def __init__(self, base_dir: Optional[Path] = None):
        self.base_dir = base_dir or DEFAULT_VOICEPACKS_DIR
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._voicepacks: Dict[str, VoicepackInfo] = {}
        self.rescan()

    def rescan(self) -> List[VoicepackInfo]:
        """Scan configured voice directories and index all valid voicepacks."""
        discovered: Dict[str, VoicepackInfo] = {}

        # Scan active storage base_dir and all configured model directories
        scan_roots = [self.base_dir]
        for extra_dir in get_all_model_scan_dirs():
            if extra_dir not in scan_roots and extra_dir.exists():
                scan_roots.append(extra_dir)
                piper_sub = extra_dir / "tts" / "piper"
                if piper_sub.exists() and piper_sub not in scan_roots:
                    scan_roots.append(piper_sub)

        for root in scan_roots:
            if not root.exists():
                continue
            try:
                for item in root.iterdir():
                    if item.is_dir() and not item.name.startswith("."):
                        vp = self._inspect_directory(item)
                        if vp and vp.id not in discovered:
                            discovered[vp.id] = vp
                    elif item.is_file() and item.suffix.lower() == ".onnx":
                        is_builtin = (root == LEGACY_MODELS_DIR)
                        vp = self._inspect_model_file(item, is_builtin=is_builtin)
                        if vp and vp.id not in discovered:
                            discovered[vp.id] = vp
            except Exception as e:
                logger.debug(f"Error scanning voicepack root '{root}': {e}")

        self._voicepacks = discovered
        logger.debug(f"Discovered {len(self._voicepacks)} voicepacks across storage directories.")
        return list(self._voicepacks.values())

    def _inspect_directory(self, folder: Path, is_builtin: bool = False) -> Optional[VoicepackInfo]:
        """Inspect a subfolder containing a voicepack."""
        onnx_files = list(folder.glob("*.onnx"))
        if not onnx_files:
            return None

        model_file = onnx_files[0]
        # Match model_file.onnx.json or folder config
        config_file = model_file.with_name(f"{model_file.name}.json")
        if not config_file.exists():
            config_file = model_file.with_suffix(".json")
        if not config_file.exists():
            # Look for any json in the folder
            jsons = list(folder.glob("*.json"))
            if jsons:
                config_file = jsons[0]
            else:
                return None

        return self._build_voicepack_info(folder.name, model_file, config_file, is_builtin=is_builtin)

    def _inspect_model_file(self, model_file: Path, is_builtin: bool = False) -> Optional[VoicepackInfo]:
        """Inspect a standalone .onnx model file and its companion .json."""
        config_file = model_file.with_name(f"{model_file.name}.json")
        if not config_file.exists():
            config_file = model_file.with_suffix(".json")
        if not config_file.exists():
            return None

        voice_id = model_file.stem
        return self._build_voicepack_info(voice_id, model_file, config_file, is_builtin=is_builtin)

    def _build_voicepack_info(
        self, voice_id: str, model_file: Path, config_file: Path, is_builtin: bool = False
    ) -> Optional[VoicepackInfo]:
        """Parse configuration JSON and construct VoicepackInfo contract."""
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                config_data = json.load(f)

            audio_cfg = config_data.get("audio", {})
            sample_rate = audio_cfg.get("sample_rate", 22050)
            num_speakers = config_data.get("num_speakers", 1)
            speaker_id_map = config_data.get("speaker_id_map", {})
            speakers = list(speaker_id_map.keys()) if speaker_id_map else ["default"]
            espeak_code = config_data.get("espeak", {}).get("voice", "en-US")
            dataset_name = config_data.get("dataset", "")

            # Pretty name formatting
            clean_name = voice_id.replace("_", " ").replace("-", " ").title()
            if dataset_name and dataset_name not in clean_name:
                clean_name = f"{clean_name} ({dataset_name})"

            total_size = model_file.stat().st_size + config_file.stat().st_size

            return VoicepackInfo(
                id=voice_id,
                name=clean_name,
                provider_id="piper",
                language=espeak_code,
                model_path=str(model_file.resolve()),
                config_path=str(config_file.resolve()),
                sample_rate=sample_rate,
                num_speakers=num_speakers,
                speakers=speakers,
                size_bytes=total_size,
                status=VoicepackStatus.INSTALLED,
                license=config_data.get("license", "Open Source / Permissive"),
                attribution=config_data.get("attribution", dataset_name or "Piper Voice Community"),
                description=f"Neural TTS model running at {sample_rate}Hz with {num_speakers} speaker timbre(s).",
                is_builtin=is_builtin,
            )
        except Exception as exc:
            logger.warning(f"Failed to parse voicepack metadata for '{voice_id}': {exc}")
            return VoicepackInfo(
                id=voice_id,
                name=voice_id,
                provider_id="piper",
                language="unknown",
                model_path=str(model_file.resolve()),
                config_path=str(config_file.resolve()),
                sample_rate=22050,
                num_speakers=1,
                speakers=["default"],
                size_bytes=model_file.stat().st_size if model_file.exists() else 0,
                status=VoicepackStatus.CORRUPTED,
                license=None,
                attribution=None,
                description=f"Corrupted or invalid metadata: {exc}",
                is_builtin=is_builtin,
            )

    def list_voicepacks(self) -> List[VoicepackInfo]:
        """List all currently indexed voicepacks."""
        return list(self._voicepacks.values())

    def get_voicepack(self, voicepack_id: str) -> Optional[VoicepackInfo]:
        """Retrieve voicepack by ID."""
        return self._voicepacks.get(voicepack_id)

    def import_from_zip(
        self, archive_source: Union[bytes, str, Path], target_name: Optional[str] = None
    ) -> Tuple[bool, str, Optional[VoicepackInfo]]:
        """
        Safely imports and extracts a voicepack .zip archive into data/models/tts/piper/.
        
        Security Protections:
        - Path traversal defense: validates that every extracted file resolves within target_dir.
        - Extension whitelist: permits only .onnx, .json, .txt, .md.
        - Size bounds: rejects archives exceeding MAX_ARCHIVE_SIZE_BYTES.
        - Atomic staging: extracts to a temporary folder, validates contents, and moves to target.
        """
        if isinstance(archive_source, bytes):
            if len(archive_source) > MAX_ARCHIVE_SIZE_BYTES:
                return False, f"Archive exceeds maximum permitted size of {MAX_ARCHIVE_SIZE_BYTES // (1024*1024)} MB.", None
            zip_file_obj = zipfile.ZipFile(BytesIO(archive_source))
        else:
            path = Path(archive_source)
            if not path.exists():
                return False, f"Source archive file '{path}' not found.", None
            if path.stat().st_size > MAX_ARCHIVE_SIZE_BYTES:
                return False, f"Archive exceeds maximum permitted size of {MAX_ARCHIVE_SIZE_BYTES // (1024*1024)} MB.", None
            zip_file_obj = zipfile.ZipFile(path)

        with zip_file_obj as zf:
            namelist = zf.namelist()
            if not namelist:
                return False, "Archive is empty.", None

            # 1. Security Check: Whitelist extensions and guard against path traversal
            onnx_files = []
            json_files = []
            for member in namelist:
                # Disallow absolute paths or parent directory traversal
                norm_path = os.path.normpath(member)
                if norm_path.startswith("..") or os.path.isabs(norm_path) or "/../" in member or "\\..\\" in member:
                    return False, f"Security Violation: Path traversal detected in archive entry '{member}'.", None

                # Disallow forbidden file extensions
                suffix = Path(member).suffix.lower()
                if suffix and suffix not in ALLOWED_EXTENSIONS:
                    return False, f"Security Violation: Prohibited file extension '{suffix}' in '{member}'. Allowed: {ALLOWED_EXTENSIONS}", None

                if suffix == ".onnx":
                    onnx_files.append(member)
                elif suffix == ".json":
                    json_files.append(member)

            # Delegate to RVC character importer if .pth weights are detected in archive
            pth_files = [m for m in namelist if Path(m).suffix.lower() == ".pth"]
            if pth_files:
                from app.voice.rvc_models import import_rvc_from_zip
                success, msg, rvc_info = import_rvc_from_zip(archive_source, target_name)
                if not success or not rvc_info:
                    return False, msg, None

                vp = VoicepackInfo(
                    id=rvc_info.id,
                    name=rvc_info.name,
                    provider_id="piper",
                    language="en-US",
                    model_path=rvc_info.model_path,
                    config_path=rvc_info.index_path or rvc_info.model_path,
                    sample_rate=22050,
                    num_speakers=1,
                    speakers=[rvc_info.character_name],
                    size_bytes=rvc_info.size_bytes,
                    status=VoicepackStatus.INSTALLED,
                    description=f"RVC Character Voice: {rvc_info.character_name}",
                    is_builtin=False,
                )
                self._voicepacks[vp.id] = vp
                return True, msg, vp

            if not onnx_files:
                return False, "Invalid voicepack: No .onnx or .pth model file found in archive.", None
            if not json_files:
                return False, "Invalid voicepack: No companion configuration .json found in archive.", None

            # Determine voicepack identifier
            first_onnx = Path(onnx_files[0])
            voicepack_id = target_name or first_onnx.stem
            # Clean identifier of dangerous characters
            voicepack_id = "".join(c for c in voicepack_id if c.isalnum() or c in ("-", "_", ".")).strip(".-_")
            if not voicepack_id:
                voicepack_id = f"voicepack-{int(os.times().elapsed)}"

            target_folder = (self.base_dir / voicepack_id).resolve()
            staging_folder = (self.base_dir / f".staging_{voicepack_id}").resolve()

            # Ensure target folder stays within self.base_dir
            if not str(target_folder).startswith(str(self.base_dir.resolve())):
                return False, "Security Violation: Invalid target directory resolution.", None

            # 2. Extract into staging folder
            try:
                if staging_folder.exists():
                    shutil.rmtree(staging_folder)
                staging_folder.mkdir(parents=True, exist_ok=True)

                for member in namelist:
                    dest_file = (staging_folder / member).resolve()
                    # Final check that dest_file is inside staging_folder
                    if not str(dest_file).startswith(str(staging_folder)):
                        raise SecurityError(f"Extraction target escapes staging boundary: {member}")
                    
                    if member.endswith("/") or member.endswith("\\"):
                        dest_file.mkdir(parents=True, exist_ok=True)
                    else:
                        dest_file.parent.mkdir(parents=True, exist_ok=True)
                        with zf.open(member) as src, open(dest_file, "wb") as dst:
                            shutil.copyfileobj(src, dst)

                # Flatten single top-level folder if archive wrapped files inside an outer folder
                staged_subdirs = [p for p in staging_folder.iterdir() if p.is_dir()]
                staged_files = [p for p in staging_folder.iterdir() if p.is_file()]
                actual_content_dir = staging_folder
                if len(staged_subdirs) == 1 and len(staged_files) == 0:
                    actual_content_dir = staged_subdirs[0]

                # 3. Validate extracted model and config
                staged_onnx = list(actual_content_dir.glob("*.onnx"))
                if not staged_onnx:
                    return False, "Extraction failed: Model file not located in archive payload.", None

                # 4. Atomic move to target folder
                if target_folder.exists():
                    shutil.rmtree(target_folder)
                
                if actual_content_dir != staging_folder:
                    shutil.move(str(actual_content_dir), str(target_folder))
                    shutil.rmtree(staging_folder, ignore_errors=True)
                else:
                    shutil.move(str(staging_folder), str(target_folder))

                # 5. Re-index voicepack
                self.rescan()
                vp = self.get_voicepack(voicepack_id)
                if not vp:
                    return False, "Voicepack extracted, but failed metadata indexing check.", None

                logger.info(f"Successfully imported voicepack '{voicepack_id}' ({vp.name}) to {target_folder}")
                return True, f"Successfully imported voicepack '{vp.name}'.", vp

            except Exception as exc:
                logger.error(f"Failed to extract voicepack '{voicepack_id}': {exc}")
                if staging_folder.exists():
                    shutil.rmtree(staging_folder, ignore_errors=True)
                return False, f"Import extraction failed: {str(exc)}", None

    def import_from_folder(
        self, folder_or_file_path: Union[str, Path], target_name: Optional[str] = None
    ) -> Tuple[bool, str, Optional[VoicepackInfo]]:
        """
        Safely imports an uncompressed voice model folder or .onnx/.pth file from any path on the system.
        Copies the model into the external active models directory so it can be managed cleanly.
        """
        source = Path(folder_or_file_path).resolve()
        if not source.exists():
            return False, f"Source path '{source}' does not exist on disk.", None

        # If a single .pth file or RVC folder is passed, delegate to RVC importer
        if (source.is_file() and source.suffix.lower() == ".pth") or (source.is_dir() and list(source.glob("*.pth"))):
            from app.voice.rvc_models import import_rvc_from_folder
            success, msg, rvc_info = import_rvc_from_folder(source, target_name)
            if not success or not rvc_info:
                return False, msg, None

            vp = VoicepackInfo(
                id=rvc_info.id,
                name=rvc_info.name,
                provider_id="piper",
                language="en-US",
                model_path=rvc_info.model_path,
                config_path=rvc_info.index_path or rvc_info.model_path,
                sample_rate=22050,
                num_speakers=1,
                speakers=[rvc_info.character_name],
                size_bytes=rvc_info.size_bytes,
                status=VoicepackStatus.INSTALLED,
                description=f"RVC Character Voice: {rvc_info.character_name}",
                is_builtin=False,
            )
            self._voicepacks[vp.id] = vp
            return True, msg, vp

        # Piper .onnx handling
        if source.is_file() and source.suffix.lower() == ".onnx":
            voicepack_id = target_name or source.stem
            target_folder = (self.base_dir / voicepack_id).resolve()
            target_folder.mkdir(parents=True, exist_ok=True)

            shutil.copy2(source, target_folder / source.name)
            cfg_name = f"{source.name}.json"
            cfg_file = source.with_name(cfg_name)
            if not cfg_file.exists():
                cfg_file = source.with_suffix(".json")
            if cfg_file.exists():
                shutil.copy2(cfg_file, target_folder / cfg_file.name)

            self.rescan()
            vp = self.get_voicepack(voicepack_id)
            if vp:
                return True, f"Successfully imported voicepack '{vp.name}' from {source}.", vp
            return True, f"Imported model to {target_folder}.", None

        if source.is_dir():
            onnx_files = list(source.glob("*.onnx"))
            if not onnx_files:
                return False, f"No .onnx or .pth model files found in '{source}'.", None

            first_onnx = onnx_files[0]
            voicepack_id = target_name or source.name
            target_folder = (self.base_dir / voicepack_id).resolve()
            target_folder.mkdir(parents=True, exist_ok=True)

            for f in source.iterdir():
                if f.is_file() and f.suffix.lower() in ALLOWED_EXTENSIONS:
                    shutil.copy2(f, target_folder / f.name)

            self.rescan()
            vp = self.get_voicepack(voicepack_id)
            if vp:
                return True, f"Successfully imported voicepack '{vp.name}' from {source}.", vp
            return True, f"Imported voicepack folder '{voicepack_id}'.", None

        return False, f"Unsupported asset path format: '{source}'", None

    def delete_voicepack(self, voicepack_id: str) -> Tuple[bool, str]:
        """Safely removes an installed voicepack from disk."""
        vp = self.get_voicepack(voicepack_id)
        if not vp:
            return False, f"Voicepack '{voicepack_id}' not found."

        if vp.is_builtin:
            return False, f"Cannot delete builtin system voicepack '{voicepack_id}'."

        model_path = Path(vp.model_path)
        parent_dir = model_path.parent

        try:
            # If the model is in its own folder inside base_dir, remove folder
            if parent_dir.resolve().parent == self.base_dir.resolve() and parent_dir != self.base_dir:
                shutil.rmtree(parent_dir)
            else:
                # Remove just the model and config files
                if model_path.exists():
                    model_path.unlink()
                config_path = Path(vp.config_path)
                if config_path.exists():
                    config_path.unlink()

            self.rescan()
            logger.info(f"Successfully deleted voicepack '{voicepack_id}'")
            return True, f"Voicepack '{voicepack_id}' has been removed."
        except Exception as exc:
            logger.error(f"Failed to delete voicepack '{voicepack_id}': {exc}")
            return False, f"Failed to delete voicepack '{voicepack_id}': {str(exc)}"


# Global singleton instance
voicepack_manager = VoicepackManager()
