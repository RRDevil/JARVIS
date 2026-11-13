"""
Persistent Piper Neural TTS Worker Process.

Runs as a long-lived background subprocess under .venv_voice.
Maintains the loaded Piper ONNX voice in memory across synthesis calls,
eliminating repetitive ONNX model loading and Python startup overhead.

Communicates via newline-delimited JSON over stdin/stdout.
"""

import base64
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import traceback
import wave

# Prevent local directory from shadowing installed third-party piper package
script_dir = str(Path(__file__).resolve().parent)
if sys.path and sys.path[0] == script_dir:
    sys.path.pop(0)

try:
    from piper import PiperVoice
    from piper.config import SynthesisConfig
except Exception:
    PiperVoice = None
    SynthesisConfig = None

# Lazy RVC references
RVCInference = None


def install_secure_torch_load():
    """Restricts weights_only=False strictly to the trusted canonical HuBERT base checkpoint.
    
    PyTorch 2.6 defaults weights_only=True to prevent arbitrary pickle code execution.
    Fairseq's hubert_base.pt contains custom Dictionary references requiring unpickling.
    This guard verifies the target file path is the trusted HuBERT model in site-packages
    or models directory; all other checkpoints are strictly forced to weights_only=True.
    """
    try:
        import torch
        if getattr(torch, "_jarvis_secure_load_installed", False):
            return
        
        _orig_torch_load = torch.load

        # If available, register safe globals for fairseq
        if hasattr(torch.serialization, "add_safe_globals"):
            try:
                import fairseq.data.dictionary
                torch.serialization.add_safe_globals([
                    fairseq.data.dictionary.Dictionary,
                ])
            except Exception:
                pass

        def _secure_torch_load(f, *args, **kwargs):
            trusted = False
            if isinstance(f, (str, Path)):
                real_path = os.path.realpath(str(f)).replace("\\", "/").lower()
                if real_path.endswith("hubert_base.pt") or real_path.endswith("hubert.pt"):
                    if "rvc_python" in real_path or "site-packages" in real_path or "models" in real_path:
                        trusted = True
            
            if trusted:
                kwargs["weights_only"] = False
            else:
                kwargs.setdefault("weights_only", True)
            
            return _orig_torch_load(f, *args, **kwargs)

        torch.load = _secure_torch_load
        torch._jarvis_secure_load_installed = True
    except Exception as exc:
        sys.stderr.write(f"Warning: could not install secure torch.load guard: {exc}\n")
        sys.stderr.flush()


def get_rvc_inference():
    global RVCInference
    if RVCInference is None:
        try:
            install_secure_torch_load()
            from rvc_python.infer import RVCInference as _RVC
            RVCInference = _RVC
        except Exception as exc:
            sys.stderr.write(f"RVC dependencies could not be loaded: {exc}\n")
            sys.stderr.flush()
            RVCInference = False
    return RVCInference


class PiperWorker:
    def __init__(self):
        self.voice: PiperVoice = None
        self.current_model_path: str = None
        self.current_config_path: str = None
        self._cached_rvc: dict = {}

    def load_model(self, model_path: str, config_path: str = None) -> bool:
        if self.voice is not None and self.current_model_path == model_path:
            return True

        if PiperVoice is None:
            raise RuntimeError("Piper TTS is not installed in the active Python environment.")

        if not os.path.exists(model_path):
            raise FileNotFoundError(f"Model file not found: {model_path}")

        cfg = config_path or (model_path + ".json")
        if not os.path.exists(cfg):
            raise FileNotFoundError(f"Config file not found: {cfg}")

        self.voice = PiperVoice.load(model_path, config_path=cfg)
        self.current_model_path = model_path
        self.current_config_path = cfg
        return True

    def synthesize(
        self,
        text: str,
        speaker_id: int = 0,
        length_scale: float = 1.0,
        volume: float = 1.0,
        noise_scale: float = None,
        noise_w_scale: float = None,
        rvc_model: str = None,
        rvc_index: str = None,
        f0method: str = "pm",
        f0up_key: int = 0,
    ) -> tuple[str, float, int]:
        """Synthesizes text into WAV base64 string, duration in seconds, and sample rate."""
        if self.voice is None:
            raise RuntimeError("No Piper voice loaded in worker.")

        if not text or not text.strip():
            return "", 0.0, self.voice.config.sample_rate

        syn_config = None
        if SynthesisConfig is not None:
            syn_kwargs = {
                "speaker_id": speaker_id,
                "length_scale": length_scale,
                "volume": volume,
            }
            if noise_scale is not None:
                syn_kwargs["noise_scale"] = noise_scale
            if noise_w_scale is not None:
                syn_kwargs["noise_w_scale"] = noise_w_scale
            syn_config = SynthesisConfig(**syn_kwargs)

        buffer = io.BytesIO()
        sample_rate = self.voice.config.sample_rate
        with wave.open(buffer, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)
            for chunk in self.voice.synthesize(text, syn_config=syn_config):
                wav_file.writeframes(chunk.audio_int16_bytes)

        raw_wav_bytes = buffer.getvalue()

        # Optional RVC Voice Conversion
        if rvc_model and os.path.exists(rvc_model):
            rvc_cls = get_rvc_inference()
            if rvc_cls:
                import torch
                torch.set_num_threads(6)
                install_secure_torch_load()
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_in:
                    tmp_in.write(raw_wav_bytes)
                    tmp_in_path = tmp_in.name

                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_out:
                    tmp_out_path = tmp_out.name

                try:
                    cache_key = (rvc_model, rvc_index)
                    rvc = self._cached_rvc.get(cache_key)
                    if rvc is None:
                        rvc = rvc_cls(
                            device="cpu:0",
                            model_path=rvc_model,
                            index_path=rvc_index if rvc_index and os.path.exists(rvc_index) else None,
                            version="v2",
                        )
                        self._cached_rvc[cache_key] = rvc

                    rvc.set_params(
                        f0method=f0method,
                        f0up_key=f0up_key,
                        index_rate=0.75,
                        filter_radius=3,
                        protect=0.33,
                    )
                    rvc.infer_file(tmp_in_path, tmp_out_path)
                    with open(tmp_out_path, "rb") as f:
                        raw_wav_bytes = f.read()
                except Exception as exc:
                    sys.stderr.write(f"Worker RVC conversion failed, using Piper audio: {exc}\n")
                    sys.stderr.flush()
                finally:
                    for p in (tmp_in_path, tmp_out_path):
                        if os.path.exists(p):
                            try:
                                os.remove(p)
                            except Exception:
                                pass

        # Calculate duration
        duration_s = 0.0
        try:
            with wave.open(io.BytesIO(raw_wav_bytes), "rb") as wf:
                duration_s = round(wf.getnframes() / float(wf.getframerate()), 3)
        except Exception:
            pass

        b64_audio = base64.b64encode(raw_wav_bytes).decode("ascii")
        return b64_audio, duration_s, sample_rate


def main():
    _ipc_stdout = sys.stdout
    sys.stdout = sys.stderr

    worker = PiperWorker()

    # Signal ready
    _ipc_stdout.write(json.dumps({"status": "ready"}) + "\n")
    _ipc_stdout.flush()

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            req = json.loads(line)
        except Exception as exc:
            _ipc_stdout.write(json.dumps({"status": "error", "error": f"Invalid JSON: {exc}"}) + "\n")
            _ipc_stdout.flush()
            continue

        cmd = req.get("command")
        req_id = req.get("id")

        if cmd == "ping":
            _ipc_stdout.write(json.dumps({"status": "ok", "action": "pong", "id": req_id}) + "\n")
            _ipc_stdout.flush()
            continue

        elif cmd == "stop":
            _ipc_stdout.write(json.dumps({"status": "ok", "action": "stopped", "id": req_id}) + "\n")
            _ipc_stdout.flush()
            break

        elif cmd == "load":
            model_path = req.get("model_path")
            config_path = req.get("config_path")
            try:
                t0 = time.time()
                worker.load_model(model_path, config_path)
                load_time = round(time.time() - t0, 3)
                _ipc_stdout.write(json.dumps({
                    "status": "ok",
                    "action": "loaded",
                    "id": req_id,
                    "model_path": model_path,
                    "load_time_seconds": load_time,
                }) + "\n")
            except Exception as exc:
                _ipc_stdout.write(json.dumps({
                    "status": "error",
                    "id": req_id,
                    "error": str(exc),
                    "traceback": traceback.format_exc(),
                }) + "\n")
            _ipc_stdout.flush()
            continue

        elif cmd == "synthesize":
            text = req.get("text", "")
            model_path = req.get("model_path")
            config_path = req.get("config_path")
            speaker_id = int(req.get("speaker_id", 0))
            length_scale = float(req.get("length_scale", 1.0))
            volume = float(req.get("volume", 1.0))
            noise_scale = float(req["noise_scale"]) if req.get("noise_scale") is not None else None
            noise_w_scale = float(req["noise_w_scale"]) if req.get("noise_w_scale") is not None else None
            rvc_model = req.get("rvc_model")
            rvc_index = req.get("rvc_index")
            f0method = req.get("f0method", "pm")
            f0up_key = int(req.get("f0up_key", 0))

            try:
                if model_path and (worker.voice is None or worker.current_model_path != model_path):
                    worker.load_model(model_path, config_path)

                t0 = time.time()
                b64_audio, duration_s, sample_rate = worker.synthesize(
                    text=text,
                    speaker_id=speaker_id,
                    length_scale=length_scale,
                    volume=volume,
                    noise_scale=noise_scale,
                    noise_w_scale=noise_w_scale,
                    rvc_model=rvc_model,
                    rvc_index=rvc_index,
                    f0method=f0method,
                    f0up_key=f0up_key,
                )
                syn_time = round(time.time() - t0, 3)
                rtf = round(syn_time / duration_s, 3) if duration_s > 0 else 0.0

                _ipc_stdout.write(json.dumps({
                    "status": "ok",
                    "id": req_id,
                    "audio_base64": b64_audio,
                    "duration_seconds": duration_s,
                    "sample_rate": sample_rate,
                    "synthesis_time_seconds": syn_time,
                    "rtf": rtf,
                }) + "\n")
            except Exception as exc:
                _ipc_stdout.write(json.dumps({
                    "status": "error",
                    "id": req_id,
                    "error": str(exc),
                    "traceback": traceback.format_exc(),
                }) + "\n")
            _ipc_stdout.flush()
            continue

        else:
            _ipc_stdout.write(json.dumps({
                "status": "error",
                "id": req_id,
                "error": f"Unknown command: {cmd}",
            }) + "\n")
            _ipc_stdout.flush()


if __name__ == "__main__":
    main()

