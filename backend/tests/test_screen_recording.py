"""Tests for Phase 5 Screen Recording Service."""

import asyncio
from pathlib import Path
import pytest
from PIL import Image

from app.perception.models import RecordingStartRequest
from app.perception.recording import ScreenRecordingService, RECORDINGS_DIR


@pytest.fixture
def recording_service(tmp_path, monkeypatch):
    service = ScreenRecordingService()
    # Direct test recordings to tmp directory
    monkeypatch.setattr("app.perception.recording.RECORDINGS_DIR", tmp_path)
    # Mock screen_capture_engine.capture to generate synthetic test frames without requiring live monitor
    def mock_capture(monitor_id=1, active_window_only=False, encode_base64=False):
        img = Image.new("RGB", (640, 360), color=(10, 20, 30))
        return img, None

    monkeypatch.setattr("app.perception.recording.screen_capture_engine.capture", mock_capture)
    return service


@pytest.mark.asyncio
async def test_initial_status(recording_service):
    status = recording_service.get_status()
    assert status.is_recording is False
    assert status.clip_id is None
    assert status.frames_captured == 0


@pytest.mark.asyncio
async def test_start_and_stop_recording(recording_service):
    req = RecordingStartRequest(duration_seconds=2, fps=5)
    status = await recording_service.start_recording(req)

    assert status.is_recording is True
    assert status.clip_id is not None
    assert status.max_duration_seconds == 2.0
    assert status.fps == 5

    # Allow recording loop to capture a couple frames
    await asyncio.sleep(0.4)

    curr_status = recording_service.get_status()
    assert curr_status.is_recording is True
    assert curr_status.frames_captured >= 1

    # Manually stop
    clip_info = await recording_service.stop_recording()
    assert clip_info is not None
    assert clip_info.clip_id == status.clip_id
    assert clip_info.format == "gif"
    assert Path(clip_info.file_path).exists()
    assert clip_info.file_size_bytes > 0

    end_status = recording_service.get_status()
    assert end_status.is_recording is False


@pytest.mark.asyncio
async def test_concurrent_recording_rejected(recording_service):
    req = RecordingStartRequest(duration_seconds=5, fps=2)
    await recording_service.start_recording(req)

    with pytest.raises(RuntimeError, match="already active"):
        await recording_service.start_recording(req)

    await recording_service.stop_recording()


@pytest.mark.asyncio
async def test_auto_stop_at_duration_limit(recording_service):
    # Short limit of 1 second
    req = RecordingStartRequest(duration_seconds=1, fps=10)
    await recording_service.start_recording(req)

    # Wait for auto-stop after 1 second
    await asyncio.sleep(1.3)

    status = recording_service.get_status()
    assert status.is_recording is False


@pytest.mark.asyncio
async def test_list_clips(recording_service, tmp_path):
    req = RecordingStartRequest(duration_seconds=1, fps=5)
    await recording_service.start_recording(req)
    await asyncio.sleep(0.3)
    clip_info = await recording_service.stop_recording()

    clips = recording_service.list_clips()
    assert len(clips) >= 1
    assert any(c.clip_id == clip_info.clip_id for c in clips)

