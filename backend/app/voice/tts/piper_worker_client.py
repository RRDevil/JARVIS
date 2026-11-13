"""
Asynchronous Client for Persistent Piper TTS Worker.

Manages the lifecycle of the persistent Piper background worker process,
serializes synthesis requests, and automatically handles idle shutdown and recovery.
"""

import asyncio
import json
import logging
import os
from pathlib import Path
import sys
from typing import Any, Dict, Optional

logger = logging.getLogger("jarvis.voice.tts.piper_worker_client")

PROJECT_ROOT = Path(__file__).resolve().parents[4]
VOICE_PYTHON_EXE = (PROJECT_ROOT / ".venv_voice" / "Scripts" / "python.exe").resolve()
WORKER_SCRIPT = (PROJECT_ROOT / "backend" / "app" / "voice" / "tts" / "piper_worker.py").resolve()

# 10 minutes idle timeout before stopping worker process to conserve memory
IDLE_TIMEOUT_SECONDS = 600


class PiperWorkerClient:
    """Manages a persistent, warm Piper neural synthesis worker subprocess."""

    def __init__(self):
        self._proc: Optional[asyncio.subprocess.Process] = None
        self._lock = asyncio.Lock()
        self._idle_task: Optional[asyncio.TimerHandle] = None
        self._request_counter = 0

    @property
    def is_running(self) -> bool:
        return self._proc is not None and self._proc.returncode is None

    async def _ensure_worker(self, runner_py: Optional[str] = None) -> None:
        """Starts the worker process if it is not currently running, or recycles if loop changed."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if self._proc is not None:
            # If the process is tied to an expired/different event loop, recycle it cleanly
            if getattr(self, "_loop", None) != loop:
                logger.info("Event loop changed or reset; recycling persistent Piper worker.")
                await self._stop_internal()
            elif self.is_running:
                return

        self._loop = loop

        py_exe = runner_py or str(VOICE_PYTHON_EXE if VOICE_PYTHON_EXE.exists() else sys.executable)
        logger.info(f"Spawning persistent Piper TTS worker: {py_exe} {WORKER_SCRIPT}")

        self._proc = await asyncio.create_subprocess_exec(
            py_exe,
            str(WORKER_SCRIPT),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            limit=64 * 1024 * 1024,  # 64 MB stream buffer for very large audio base64 lines
        )

        # Wait for worker "ready" signal
        try:
            ready_line = await asyncio.wait_for(self._proc.stdout.readline(), timeout=10.0)
            if not ready_line:
                raise RuntimeError("Piper worker exited unexpectedly during startup.")
            ready_data = json.loads(ready_line.decode().strip())
            if ready_data.get("status") != "ready":
                raise RuntimeError(f"Unexpected initial response from Piper worker: {ready_data}")
            logger.info("Persistent Piper TTS worker is ready.")
        except Exception as exc:
            logger.error(f"Failed to start persistent Piper TTS worker: {exc}")
            await self.stop()
            raise

    def _reset_idle_timer(self) -> None:
        """Resets the inactivity shutdown timer."""
        if self._idle_task:
            self._idle_task.cancel()
            self._idle_task = None

        try:
            loop = getattr(self, "_loop", None) or asyncio.get_running_loop()
            self._idle_task = loop.call_later(
                IDLE_TIMEOUT_SECONDS,
                lambda: asyncio.create_task(self._on_idle_timeout()),
            )
        except Exception:
            pass

    async def _on_idle_timeout(self) -> None:
        """Shuts down worker after prolonged inactivity to free memory."""
        async with self._lock:
            if self.is_running:
                logger.info(f"Piper worker idle for {IDLE_TIMEOUT_SECONDS}s. Shutting down to conserve memory.")
                await self._stop_internal()

    async def synthesize(
        self,
        model_path: str,
        config_path: str,
        text: str,
        speaker_id: int = 0,
        length_scale: float = 1.0,
        volume: float = 1.0,
        noise_scale: Optional[float] = None,
        noise_w_scale: Optional[float] = None,
        rvc_model: Optional[str] = None,
        rvc_index: Optional[str] = None,
        f0method: str = "pm",
        f0up_key: int = 0,
        runner_py: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Submits a synthesis request to the warm worker process and returns the parsed result."""
        base_timeout = 180.0 if rvc_model else 45.0
        char_timeout = (len(text) / 100.0) * (2.0 if rvc_model else 0.5)
        effective_timeout = timeout if timeout is not None else max(base_timeout, base_timeout + char_timeout)

        async with self._lock:
            await self._ensure_worker(runner_py)
            self._reset_idle_timer()

            self._request_counter += 1
            req_id = f"syn-{self._request_counter}"

            req_payload = {
                "command": "synthesize",
                "id": req_id,
                "model_path": model_path,
                "config_path": config_path,
                "text": text,
                "speaker_id": speaker_id,
                "length_scale": length_scale,
                "volume": volume,
                "rvc_model": rvc_model,
                "rvc_index": rvc_index,
                "f0method": f0method,
                "f0up_key": f0up_key,
            }
            if noise_scale is not None:
                req_payload["noise_scale"] = noise_scale
            if noise_w_scale is not None:
                req_payload["noise_w_scale"] = noise_w_scale

            try:
                line_to_send = (json.dumps(req_payload) + "\n").encode("utf-8")
                self._proc.stdin.write(line_to_send)
                await self._proc.stdin.drain()

                while True:
                    resp_line = await asyncio.wait_for(self._proc.stdout.readline(), timeout=effective_timeout)
                    if not resp_line:
                        raise RuntimeError("Piper worker connection closed abruptly.")

                    line_str = resp_line.decode("utf-8").strip()
                    if not line_str:
                        continue

                    try:
                        resp = json.loads(line_str)
                    except json.JSONDecodeError:
                        logger.warning(f"Skipping non-JSON output from Piper worker: {line_str[:100]}")
                        continue

                    if resp.get("status") != "ok":
                        raise RuntimeError(f"Piper worker error: {resp.get('error', 'unknown error')}")

                    return resp
            except Exception as exc:
                logger.warning(f"Error during Piper worker synthesis: {exc}. Killing worker.")
                await self._stop_internal()
                raise

    async def _stop_internal(self) -> None:
        """Internal worker termination without acquiring lock."""
        if self._idle_task:
            self._idle_task.cancel()
            self._idle_task = None

        if self._proc is not None:
            proc = self._proc
            self._proc = None
            try:
                if proc.returncode is None:
                    proc.stdin.write(b'{"command": "stop"}\n')
                    await proc.stdin.drain()
                    try:
                        await asyncio.wait_for(proc.wait(), timeout=2.0)
                    except asyncio.TimeoutError:
                        proc.kill()
                        await proc.wait()
            except Exception as exc:
                logger.debug(f"Error terminating Piper worker: {exc}")
                try:
                    proc.kill()
                except Exception:
                    pass

    async def stop(self) -> None:
        """Gracefully halts the persistent worker process."""
        async with self._lock:
            await self._stop_internal()


# Global Singleton instance
piper_worker = PiperWorkerClient()

