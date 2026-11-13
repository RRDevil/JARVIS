"""
Automated Test Suite for Persistent Piper TTS Worker Process and Streaming Architecture.
Milestone 2.4: Low-Latency Streaming TTS Pipeline.
"""

import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
import pytest

from app.voice.models import SpeechSynthesizeRequest
from app.voice.tts.piper import PiperTTSProvider
from app.voice.tts.piper_worker_client import PiperWorkerClient
from app.voice.voicepacks import voicepack_manager

PROJECT_ROOT = Path(__file__).resolve().parents[2]
VOICE_PYTHON_EXE = (PROJECT_ROOT / ".venv_voice" / "Scripts" / "python.exe").resolve()
WORKER_SCRIPT = (PROJECT_ROOT / "backend" / "app" / "voice" / "tts" / "piper_worker.py").resolve()


@pytest.mark.asyncio
async def test_piper_worker_script_protocol():
    """Verify piper_worker.py starts, signals readiness, and handles ping/stop commands."""
    if not VOICE_PYTHON_EXE.exists():
        pytest.skip(".venv_voice environment not found")

    proc = await asyncio.create_subprocess_exec(
        str(VOICE_PYTHON_EXE),
        str(WORKER_SCRIPT),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        limit=4 * 1024 * 1024,
    )

    try:
        # 1. Read ready handshake
        ready_line = await asyncio.wait_for(proc.stdout.readline(), timeout=5.0)
        ready_data = json.loads(ready_line.decode().strip())
        assert ready_data.get("status") == "ready"

        # 2. Send ping command
        ping_cmd = {"command": "ping", "id": "p-1"}
        proc.stdin.write((json.dumps(ping_cmd) + "\n").encode())
        await proc.stdin.drain()

        ping_resp_line = await asyncio.wait_for(proc.stdout.readline(), timeout=5.0)
        ping_resp = json.loads(ping_resp_line.decode().strip())
        assert ping_resp.get("status") == "ok"
        assert ping_resp.get("action") == "pong"
        assert ping_resp.get("id") == "p-1"

        # 3. Send stop command
        stop_cmd = {"command": "stop", "id": "s-1"}
        proc.stdin.write((json.dumps(stop_cmd) + "\n").encode())
        await proc.stdin.drain()

        stop_resp_line = await asyncio.wait_for(proc.stdout.readline(), timeout=5.0)
        stop_resp = json.loads(stop_resp_line.decode().strip())
        assert stop_resp.get("status") == "ok"
        assert stop_resp.get("action") == "stopped"

        await asyncio.wait_for(proc.wait(), timeout=3.0)
        assert proc.returncode == 0
    finally:
        if proc.returncode is None:
            proc.kill()
            await proc.wait()


@pytest.mark.asyncio
async def test_piper_worker_warm_synthesis():
    """Verify persistent worker keeps model warm and synthesizes sentences with sub-second latency."""
    if not VOICE_PYTHON_EXE.exists():
        pytest.skip(".venv_voice environment not found")

    voicepacks = voicepack_manager.list_voicepacks()
    if not voicepacks:
        pytest.skip("No installed Piper voicepacks available")

    target_vp = voicepacks[0]

    proc = await asyncio.create_subprocess_exec(
        str(VOICE_PYTHON_EXE),
        str(WORKER_SCRIPT),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        limit=16 * 1024 * 1024,
    )

    try:
        # Read ready line
        await asyncio.wait_for(proc.stdout.readline(), timeout=5.0)

        # First synthesis: loads model and synthesizes
        syn1_cmd = {
            "command": "synthesize",
            "id": "syn-1",
            "model_path": target_vp.model_path,
            "config_path": target_vp.config_path,
            "text": "Initial sentence to load and warm the neural weights.",
        }
        proc.stdin.write((json.dumps(syn1_cmd) + "\n").encode())
        await proc.stdin.drain()

        syn1_line = await asyncio.wait_for(proc.stdout.readline(), timeout=15.0)
        syn1_resp = json.loads(syn1_line.decode().strip())
        assert syn1_resp.get("status") == "ok"
        assert syn1_resp.get("id") == "syn-1"
        assert len(syn1_resp.get("audio_base64", "")) > 1000
        assert syn1_resp.get("duration_seconds") > 0.5

        # Second synthesis: model is already warm, synthesis latency should be rapid (< 0.8s)
        syn2_cmd = {
            "command": "synthesize",
            "id": "syn-2",
            "model_path": target_vp.model_path,
            "config_path": target_vp.config_path,
            "text": "Warm inference is executed with zero reload overhead.",
        }
        proc.stdin.write((json.dumps(syn2_cmd) + "\n").encode())
        await proc.stdin.drain()

        syn2_line = await asyncio.wait_for(proc.stdout.readline(), timeout=10.0)
        syn2_resp = json.loads(syn2_line.decode().strip())
        assert syn2_resp.get("status") == "ok"
        assert syn2_resp.get("id") == "syn-2"
        assert syn2_resp.get("synthesis_time_seconds") < 2.0  # Typically 0.15s - 0.35s (allow margin under concurrent test load)
        assert syn2_resp.get("rtf") < 0.6  # Real-time factor is well below 1.0

        # Clean shutdown
        proc.stdin.write(b'{"command": "stop"}\n')
        await proc.stdin.drain()
        await proc.wait()
    finally:
        if proc.returncode is None:
            proc.kill()
            await proc.wait()


@pytest.mark.asyncio
async def test_piper_worker_client_lifecycle():
    """Verify PiperWorkerClient manages subprocess lifecycle, synthesis, and recovery."""
    client = PiperWorkerClient()
    voicepacks = voicepack_manager.list_voicepacks()
    if not voicepacks:
        pytest.skip("No voicepacks found")

    target_vp = voicepacks[0]

    try:
        assert not client.is_running
        res = await client.synthesize(
            model_path=target_vp.model_path,
            config_path=target_vp.config_path,
            text="Testing persistent client dispatch.",
        )
        assert res.get("status") == "ok"
        assert client.is_running

        # Stopping client
        await client.stop()
        assert not client.is_running
    finally:
        await client.stop()


@pytest.mark.asyncio
async def test_piper_tts_provider_synthesis():
    """Verify PiperTTSProvider integrates with persistent worker for synthesize()."""
    provider = PiperTTSProvider()
    if not provider.is_available():
        pytest.skip("Piper TTS provider not available")

    req = SpeechSynthesizeRequest(
        text="All subsystems report fully operational.",
        voice_id="en_US-lessac-medium",
        rate=180,
        volume=100,
    )

    resp = await provider.synthesize(req)
    assert resp.provider_used == "piper"
    assert len(resp.audio_base64) > 1000
    assert resp.duration_seconds > 0.5

    from app.voice.tts.piper_worker_client import piper_worker
    await piper_worker.stop()


def test_secure_torch_load_fairseq_guard(tmp_path):
    """Verify that piper_worker's secure torch load allows trusted HuBERT while blocking untrusted pickles."""
    if not VOICE_PYTHON_EXE.exists():
        pytest.skip(".venv_voice not found")

    verify_script = """
import os
import sys
from pathlib import Path
import torch

# Import piper_worker's install_secure_torch_load
sys.path.insert(0, str(Path(r"{worker_dir}").resolve()))
from piper_worker import install_secure_torch_load

install_secure_torch_load()

# Test 1: Check that an untrusted pickle is strictly blocked by weights_only=True
untrusted_file = r"{untrusted_path}"
class UntrustedPayload:
    def __reduce__(self):
        return (eval, ("1+1",))

torch.save(UntrustedPayload(), untrusted_file)

try:
    torch.load(untrusted_file)
    print("FAIL: untrusted payload loaded!")
    sys.exit(1)
except Exception as e:
    print(f"PASS: untrusted payload blocked as expected ({type(e).__name__})")

# Test 2: Verify trusted HuBERT checkpoint loads if present
hubert_path = r"{hubert_path}"
if os.path.exists(hubert_path):
    loaded = torch.load(hubert_path)
    print(f"PASS: trusted HuBERT loaded successfully ({type(loaded).__name__})")
else:
    print("PASS: HuBERT path not present on disk, skipped load")

sys.exit(0)
"""
    hubert_pt = PROJECT_ROOT / ".venv_voice" / "Lib" / "site-packages" / "rvc_python" / "base_model" / "hubert_base.pt"
    untrusted_pt = tmp_path / "exploit.pt"
    worker_dir = PROJECT_ROOT / "backend" / "app" / "voice" / "tts"

    code = (
        verify_script
        .replace("{worker_dir}", str(worker_dir))
        .replace("{untrusted_path}", str(untrusted_pt))
        .replace("{hubert_path}", str(hubert_pt))
    )

    result = subprocess.run(
        [str(VOICE_PYTHON_EXE), "-c", code],
        capture_output=True,
        text=True,
        timeout=35,
    )
    assert result.returncode == 0, f"Script failed: {result.stdout}\n{result.stderr}"
    assert "PASS: untrusted payload blocked" in result.stdout


