"""Bounded Debugging Screen Recording Service (Phase 5).

Captures short, bounded desktop video clips (animated GIF format)
for debugging, visual verification, and interaction auditing without
cloud uploads or unconstrained background recording.
"""

import asyncio
from datetime import datetime, timezone
import io
import logging
import os
from pathlib import Path
import time
from typing import List, Optional
import uuid

from PIL import Image

from app.core.config import settings
from app.perception.models import (
    RecordingClipInfo,
    RecordingStartRequest,
    RecordingStatus,
)
from app.perception.screen_capture import screen_capture_engine

logger = logging.getLogger("jarvis.perception.recording")

RECORDINGS_DIR = (settings.workspace_path / "recordings").resolve()


class ScreenRecordingService:
    """Manages bounded screen recording clips for desktop interaction debugging."""

    def __init__(self):
        self._is_recording = False
        self._current_clip_id: Optional[str] = None
        self._start_time: float = 0.0
        self._duration_limit: float = 5.0
        self._fps: int = 5
        self._monitor_id: int = 1
        self._active_window_only: bool = False
        self._frames: List[Image.Image] = []
        self._record_task: Optional[asyncio.Task] = None
        self._last_exported_clip: Optional[RecordingClipInfo] = None
        self._lock = asyncio.Lock()

        # Ensure storage directory exists
        RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)

    @property
    def is_recording(self) -> bool:
        return self._is_recording

    def get_status(self) -> RecordingStatus:
        """Query current state of the screen recorder."""
        elapsed = time.time() - self._start_time if self._is_recording else 0.0
        return RecordingStatus(
            is_recording=self._is_recording,
            clip_id=self._current_clip_id,
            elapsed_seconds=round(elapsed, 2),
            max_duration_seconds=self._duration_limit,
            fps=self._fps,
            frames_captured=len(self._frames),
            file_path=self._last_exported_clip.file_path if self._last_exported_clip else None,
        )

    async def start_recording(self, request: RecordingStartRequest) -> RecordingStatus:
        """Initiate a bounded screen recording session."""
        async with self._lock:
            if self._is_recording:
                raise RuntimeError("Screen recording is already active.")

            self._is_recording = True
            self._current_clip_id = f"clip-{datetime.now().strftime('%Y%m%d_%H%M%S')}-{uuid.uuid4().hex[:6]}"
            self._start_time = time.time()
            self._duration_limit = float(min(30, max(1, request.duration_seconds)))
            self._fps = min(15, max(1, request.fps))
            self._monitor_id = request.monitor_id
            self._active_window_only = request.active_window_only
            self._frames = []

            logger.info(
                f"Starting bounded screen recording [{self._current_clip_id}] "
                f"(max {self._duration_limit}s @ {self._fps} fps)"
            )

            # Spawn bounded recording background loop
            self._record_task = asyncio.create_task(self._recording_loop())
            return self.get_status()

    async def _recording_loop(self) -> None:
        """Asynchronous capture loop respecting frame rate and duration limit."""
        interval = 1.0 / float(self._fps)
        try:
            while self._is_recording:
                now = time.time()
                elapsed = now - self._start_time

                if elapsed >= self._duration_limit:
                    logger.info(f"Screen recording [{self._current_clip_id}] reached limit ({self._duration_limit}s). Stopping.")
                    break

                # Capture frame
                try:
                    img, _ = screen_capture_engine.capture(
                        monitor_id=self._monitor_id,
                        active_window_only=self._active_window_only,
                        encode_base64=False,
                    )
                    # Downscale if larger than 1280x720 to conserve memory and encoding time
                    max_w, max_h = 1280, 720
                    if img.width > max_w or img.height > max_h:
                        img.thumbnail((max_w, max_h), Image.Resampling.BILINEAR)

                    self._frames.append(img.convert("RGB"))
                except Exception as exc:
                    logger.warning(f"Error grabbing recording frame: {exc}")

                # Sleep to maintain FPS
                cycle_time = time.time() - now
                sleep_time = max(0.01, interval - cycle_time)
                await asyncio.sleep(sleep_time)

        except asyncio.CancelledError:
            logger.info(f"Recording loop [{self._current_clip_id}] cancelled.")
        finally:
            await self._finalize_recording()

    async def stop_recording(self) -> Optional[RecordingClipInfo]:
        """Manually halt active recording and export the captured frames."""
        async with self._lock:
            if not self._is_recording:
                return self._last_exported_clip

            self._is_recording = False
            if self._record_task and not self._record_task.done():
                self._record_task.cancel()

            return await self._finalize_recording()

    async def _finalize_recording(self) -> Optional[RecordingClipInfo]:
        """Encode captured frames into an animated GIF on local disk."""
        self._is_recording = False
        clip_id = self._current_clip_id
        frames = list(self._frames)
        self._frames = []

        if not frames or not clip_id:
            logger.info("No frames to export for recording.")
            return None

        t0 = time.perf_counter()
        file_name = f"{clip_id}.gif"
        output_path = RECORDINGS_DIR / file_name

        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                None,
                self._save_gif,
                frames,
                output_path,
                int(1000 / self._fps),
            )

            file_size = output_path.stat().st_size
            duration_s = round(len(frames) / float(self._fps), 2)
            export_time = round((time.perf_counter() - t0) * 1000, 1)

            logger.info(
                f"Exported recording clip to {output_path} ({len(frames)} frames, "
                f"{duration_s}s, {file_size / 1024:.1f} KB in {export_time}ms)"
            )

            clip_info = RecordingClipInfo(
                clip_id=clip_id,
                created_at=datetime.now(timezone.utc).isoformat(),
                duration_seconds=duration_s,
                file_size_bytes=file_size,
                file_path=str(output_path),
                format="gif",
            )
            self._last_exported_clip = clip_info
            return clip_info
        except Exception as exc:
            logger.error(f"Failed to export recording clip: {exc}")
            return None

    def _save_gif(self, frames: List[Image.Image], output_path: Path, frame_duration_ms: int) -> None:
        """Synchronously encode and save frames as animated GIF."""
        if not frames:
            return
        first = frames[0]
        first.save(
            str(output_path),
            save_all=True,
            append_images=frames[1:],
            duration=frame_duration_ms,
            loop=0,
            optimize=True,
        )

    def list_clips(self) -> List[RecordingClipInfo]:
        """List previously exported local debugging clips."""
        clips: List[RecordingClipInfo] = []
        if not RECORDINGS_DIR.exists():
            return clips

        for p in sorted(RECORDINGS_DIR.glob("*.gif"), key=lambda f: f.stat().st_mtime, reverse=True):
            stat = p.stat()
            clips.append(
                RecordingClipInfo(
                    clip_id=p.stem,
                    created_at=datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
                    duration_seconds=0.0,
                    file_size_bytes=stat.st_size,
                    file_path=str(p),
                    format="gif",
                )
            )
        return clips


# Global Singleton Instance
screen_recording_service = ScreenRecordingService()

