"""
RVC Character Voice Model Discovery and Asset Management Subsystem.
Enables automatic zero-code discovery and safe in-app importing of community RVC character models (.pth + .index).
"""

from io import BytesIO
import logging
import os
from pathlib import Path
import re
import shutil
from typing import Dict, List, Optional, Tuple, Union
import zipfile
from pydantic import BaseModel, Field

from app.voice.paths import get_rvc_models_dir, get_all_model_scan_dirs

logger = logging.getLogger("jarvis.voice.rvc_models")

PROJECT_ROOT = Path(__file__).resolve().parents[3]
RVC_STORAGE_DIR = get_rvc_models_dir()
LEGACY_MODELS_DIR = (PROJECT_ROOT / "engines" / "voice_eval" / "models").resolve()

RVC_ALLOWED_EXTENSIONS = {".pth", ".index", ".json", ".txt", ".md"}
MAX_ARCHIVE_SIZE_BYTES = 500 * 1024 * 1024  # 500 MB


class RVCModelInfo(BaseModel):
    """Metadata describing a discovered or imported RVC character model."""

    id: str = Field(..., description="Unique slug identifier (e.g. rvc-kasane-teto).")
    character_name: str = Field(..., description="Clean character display name.")
    name: str = Field(..., description="Full profile display name.")
    model_path: str = Field(..., description="Absolute path to .pth weights checkpoint.")
    index_path: Optional[str] = Field(None, description="Absolute path to companion .index file if present.")
    size_bytes: int = Field(default=0, description="Model file size in bytes.")


def clean_character_name(raw: str) -> str:
    """Sanitize directory or model stem into a human-readable character name."""
    cleaned = re.sub(r"\[.*?\]", "", raw)
    cleaned = re.sub(r"\(.*?\)", "", cleaned)
    cleaned = cleaned.replace("_", " ").replace("-", " ").strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned or raw


def slugify(text: str) -> str:
    """Generate safe alphanumeric hyphenated slug."""
    slug = re.sub(r"[^a-zA-Z0-9_\-]+", "-", text).strip("-").lower()
    return slug or "rvc-character"


def scan_rvc_models() -> List[RVCModelInfo]:
    """
    Scans configured model directories for .pth checkpoints and companion .index files.
    Discovers models in:
    1. data/models/voice/rvc/ (primary user/import storage)
    2. engines/voice_eval/models/ (legacy/evaluated character models)
    """
    RVC_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    scan_dirs = [RVC_STORAGE_DIR]
    for extra_dir in get_all_model_scan_dirs():
        if extra_dir not in scan_dirs and extra_dir.exists():
            scan_dirs.append(extra_dir)
            rvc_sub = extra_dir / "voice" / "rvc"
            if rvc_sub.exists() and rvc_sub not in scan_dirs:
                scan_dirs.append(rvc_sub)
    if LEGACY_MODELS_DIR not in scan_dirs and LEGACY_MODELS_DIR.exists():
        scan_dirs.append(LEGACY_MODELS_DIR)
    discovered: Dict[str, RVCModelInfo] = {}

    for root_dir in scan_dirs:
        if not root_dir.exists():
            continue

        for pth in root_dir.rglob("*.pth"):
            folder = pth.parent

            # Look for companion .index file in same folder or parent folder
            index_files = list(folder.glob("*.index"))
            if not index_files and folder.parent != root_dir:
                index_files = list(folder.parent.glob("*.index"))
            index_path = str(index_files[0].resolve()) if index_files else None

            raw_name = pth.stem
            if raw_name.lower() in ("model", "weights", "checkpoint"):
                raw_name = folder.name

            # Name exactly as file name
            exact_name = raw_name
            slug = slugify(exact_name)
            model_id = f"rvc-{slug}"

            # If already discovered in primary storage, prioritize it over external/legacy
            if model_id in discovered and root_dir != RVC_STORAGE_DIR:
                continue

            discovered[model_id] = RVCModelInfo(
                id=model_id,
                character_name=exact_name,
                name=exact_name,
                model_path=str(pth.resolve()),
                index_path=index_path,
                size_bytes=pth.stat().st_size if pth.exists() else 0,
            )

    return list(discovered.values())


def get_rvc_model(model_id_or_path: str) -> Optional[RVCModelInfo]:
    """Lookup an RVC model by its ID, character name, filename stem, or file path."""
    models = scan_rvc_models()
    target_clean = model_id_or_path.lower().replace("rvc-", "").replace("_", "-").replace(" ", "-")
    for m in models:
        if m.id == model_id_or_path or m.model_path == model_id_or_path:
            return m
        m_clean = m.id.lower().replace("rvc-", "").replace("_", "-").replace(" ", "-")
        if m_clean == target_clean:
            return m
        if Path(m.model_path).stem.lower() == Path(model_id_or_path).stem.lower():
            return m
    # Partial substring fallback
    for m in models:
        m_clean = m.id.lower().replace("rvc-", "").replace("_", "-").replace(" ", "-")
        if target_clean in m_clean or m_clean in target_clean:
            return m
    return None


def import_rvc_from_zip(
    archive_source: Union[bytes, str, Path], target_name: Optional[str] = None
) -> Tuple[bool, str, Optional[RVCModelInfo]]:
    """
    Safely unpacks and registers a community RVC character voice .zip archive.
    Security features:
    - Path traversal validation
    - Extension whitelist (.pth, .index, .json, .txt, .md)
    - File size bound (<= 500 MB)
    - Atomic extraction into staging folder
    """
    if isinstance(archive_source, bytes):
        if len(archive_source) > MAX_ARCHIVE_SIZE_BYTES:
            return False, f"Archive exceeds {MAX_ARCHIVE_SIZE_BYTES // (1024*1024)} MB limit.", None
        zip_file_obj = zipfile.ZipFile(BytesIO(archive_source))
    else:
        path = Path(archive_source)
        if not path.exists():
            return False, f"Source archive file '{path}' not found.", None
        if path.stat().st_size > MAX_ARCHIVE_SIZE_BYTES:
            return False, f"Archive exceeds {MAX_ARCHIVE_SIZE_BYTES // (1024*1024)} MB limit.", None
        zip_file_obj = zipfile.ZipFile(path)

    with zip_file_obj as zf:
        namelist = zf.namelist()
        if not namelist:
            return False, "Archive is empty.", None

        pth_files = []
        for member in namelist:
            norm_path = os.path.normpath(member)
            if norm_path.startswith("..") or os.path.isabs(norm_path) or "/../" in member or "\\..\\" in member:
                return False, f"Security Violation: Path traversal detected in entry '{member}'.", None

            suffix = Path(member).suffix.lower()
            if suffix and suffix not in RVC_ALLOWED_EXTENSIONS:
                return False, f"Security Violation: Prohibited file extension '{suffix}' in archive.", None

            if suffix == ".pth":
                pth_files.append(member)

        if not pth_files:
            return False, "Invalid RVC archive: No .pth model weights file found in archive.", None

        first_pth = Path(pth_files[0])
        char_raw = target_name or (first_pth.stem if first_pth.stem.lower() not in ("model", "weights") else first_pth.parent.name)
        char_name = clean_character_name(char_raw)
        slug = slugify(char_name)

        target_folder = (RVC_STORAGE_DIR / slug).resolve()
        staging_folder = (RVC_STORAGE_DIR / f".staging_{slug}").resolve()

        if not str(target_folder).startswith(str(RVC_STORAGE_DIR)):
            return False, "Security Violation: Target directory resolution escaped storage.", None

        try:
            if staging_folder.exists():
                shutil.rmtree(staging_folder)
            staging_folder.mkdir(parents=True, exist_ok=True)

            for member in namelist:
                dest_file = (staging_folder / member).resolve()
                if not str(dest_file).startswith(str(staging_folder)):
                    raise SecurityError(f"Extraction escapes staging directory: {member}")

                if member.endswith("/") or member.endswith("\\"):
                    dest_file.mkdir(parents=True, exist_ok=True)
                else:
                    dest_file.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(member) as src, open(dest_file, "wb") as dst:
                        shutil.copyfileobj(src, dst)

            # Move atomically from staging to target
            if target_folder.exists():
                shutil.rmtree(target_folder)
            staging_folder.rename(target_folder)

        except Exception as exc:
            if staging_folder.exists():
                shutil.rmtree(staging_folder, ignore_errors=True)
            logger.error(f"Failed extracting RVC archive: {exc}")
            return False, f"Extraction failed: {exc}", None

        # Re-scan to find newly imported model
        models = scan_rvc_models()
        imported = next((m for m in models if m.id == f"rvc-{slug}" or slug in m.id), None)
        if not imported:
            # Fallback search
            imported = next((m for m in models if slug in m.model_path.lower()), None)

        msg = f"Successfully imported RVC character voice '{char_name}'."
        return True, msg, imported


def import_rvc_from_folder(
    source_path: Union[str, Path], target_name: Optional[str] = None
) -> Tuple[bool, str, Optional[RVCModelInfo]]:
    """
    Safely registers or imports an on-disk RVC model folder or .pth file into the active external models directory.
    """
    source = Path(source_path).resolve()
    if not source.exists():
        return False, f"Source RVC path '{source}' not found on disk.", None

    pth_file: Optional[Path] = None
    index_file: Optional[Path] = None

    if source.is_file() and source.suffix.lower() == ".pth":
        pth_file = source
        # Look for companion index in same directory
        indexes = list(source.parent.glob("*.index"))
        if indexes:
            index_file = indexes[0]
    elif source.is_dir():
        pths = list(source.rglob("*.pth"))
        if not pths:
            return False, f"No .pth model weights found in directory '{source}'.", None
        pth_file = pths[0]
        indexes = list(source.rglob("*.index"))
        if indexes:
            index_file = indexes[0]
    else:
        return False, f"Invalid RVC model path '{source}'.", None

    char_name = target_name or clean_character_name(pth_file.stem)
    slug = slugify(target_name or pth_file.stem)
    target_folder = (RVC_STORAGE_DIR / slug).resolve()

    # If already residing in RVC_STORAGE_DIR or scan roots, simply register
    if RVC_STORAGE_DIR.resolve() in pth_file.parents:
        models = scan_rvc_models()
        matched = next((m for m in models if m.model_path == str(pth_file.resolve())), None)
        if matched:
            return True, f"RVC model '{matched.name}' registered.", matched

    try:
        target_folder.mkdir(parents=True, exist_ok=True)
        target_pth = target_folder / pth_file.name
        if target_pth.resolve() != pth_file.resolve():
            shutil.copy2(pth_file, target_pth)

        if index_file and index_file.exists():
            target_idx = target_folder / index_file.name
            if target_idx.resolve() != index_file.resolve():
                shutil.copy2(index_file, target_idx)

        models = scan_rvc_models()
        imported = next((m for m in models if m.model_path == str(target_pth.resolve())), None)
        if not imported:
            imported = next((m for m in models if m.id == f"rvc-{slug}" or slug in m.id), None)
        if not imported:
            imported = next((m for m in models if slug in m.model_path.lower()), None)
        if not imported:
            imported = RVCModelInfo(
                id=f"rvc-{slug}",
                character_name=char_name,
                name=char_name,
                model_path=str(target_pth.resolve()),
                index_path=str(target_folder / index_file.name) if index_file and index_file.exists() else None,
                size_bytes=target_pth.stat().st_size if target_pth.exists() else 0,
            )

        return True, f"Successfully imported RVC voice '{char_name}'.", imported
    except Exception as exc:
        logger.error(f"Failed copying RVC model files from '{source}': {exc}")
        return False, f"Failed copying RVC model: {str(exc)}", None

