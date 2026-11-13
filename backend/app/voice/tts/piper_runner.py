"""
Lightweight Piper TTS Synthesis Runner with Optional RVC Post-Processing.
Can be executed under .venv_voice or in-process to synthesize WAV audio.
"""

import argparse
import base64
import io
import os
from pathlib import Path
import sys
import tempfile
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

# Optional RVC support is imported lazily inside synthesize_to_wav_bytes
# to keep pure Piper startup fast and avoid heavy PyTorch initialization overhead.
RVCInference = None


def synthesize_to_wav_bytes(
    model_path: str,
    config_path: str,
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
) -> bytes:
    if PiperVoice is None:
        raise RuntimeError("Piper TTS is not installed in the active Python environment.")

    voice = PiperVoice.load(model_path, config_path=config_path)
    buffer = io.BytesIO()

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

    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(voice.config.sample_rate)
        for chunk in voice.synthesize(text, syn_config=syn_config):
            wav_file.writeframes(chunk.audio_int16_bytes)

    piper_bytes = buffer.getvalue()

    # Optional RVC Voice Conversion
    if rvc_model and os.path.exists(rvc_model):
        global RVCInference
        if RVCInference is None:
            try:
                import torch
                _orig_torch_load = torch.load

                if hasattr(torch.serialization, "add_safe_globals"):
                    try:
                        import fairseq.data.dictionary
                        torch.serialization.add_safe_globals([fairseq.data.dictionary.Dictionary])
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
                from rvc_python.infer import RVCInference as _RVC
                RVCInference = _RVC
            except Exception as exc:
                sys.stderr.write(f"RVC dependencies could not be loaded: {exc}\n")
                RVCInference = False

        if RVCInference:
            import torch
            torch.set_num_threads(6)
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_in:
            tmp_in.write(piper_bytes)
            tmp_in_path = tmp_in.name

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_out:
            tmp_out_path = tmp_out.name

        try:
            rvc = RVCInference(
                device="cpu:0",
                model_path=rvc_model,
                index_path=rvc_index if rvc_index and os.path.exists(rvc_index) else None,
                version="v2",
            )
            rvc.set_params(
                f0method=f0method,
                f0up_key=f0up_key,
                index_rate=0.75,
                filter_radius=3,
                protect=0.33,
            )
            rvc.infer_file(tmp_in_path, tmp_out_path)
            with open(tmp_out_path, "rb") as f:
                return f.read()
        except Exception as exc:
            sys.stderr.write(f"RVC conversion failed, falling back to Piper audio: {exc}\n")
            return piper_bytes
        finally:
            for p in (tmp_in_path, tmp_out_path):
                if os.path.exists(p):
                    try:
                        os.remove(p)
                    except Exception:
                        pass

    return piper_bytes


def main():
    parser = argparse.ArgumentParser(description="Piper TTS CLI Runner")
    parser.add_argument("--model", required=True, help="Path to .onnx model")
    parser.add_argument("--config", required=True, help="Path to .json config")
    parser.add_argument("--text", required=True, help="Text string to speak")
    parser.add_argument("--speaker", type=int, default=0, help="Speaker index")
    parser.add_argument("--length-scale", type=float, default=1.0, help="Speed adjustment (lower = faster)")
    parser.add_argument("--volume", type=float, default=1.0, help="Volume scale (0.0 to 1.0)")
    parser.add_argument("--noise-scale", type=float, default=None, help="Phoneme variation noise scale")
    parser.add_argument("--noise-w-scale", type=float, default=None, help="Phoneme width noise scale")
    parser.add_argument("--rvc-model", help="Optional path to .pth RVC character model")
    parser.add_argument("--rvc-index", help="Optional path to .index RVC index file")
    parser.add_argument("--f0method", default="pm", help="Pitch method (pm, harvest, rmvpe)")
    parser.add_argument("--f0up-key", type=int, default=0, help="Pitch shift in semitones")
    parser.add_argument("--output", help="Output WAV path (or prints base64 if omitted)")
    args = parser.parse_args()

    wav_bytes = synthesize_to_wav_bytes(
        args.model,
        args.config,
        args.text,
        speaker_id=args.speaker,
        length_scale=args.length_scale,
        volume=args.volume,
        noise_scale=args.noise_scale,
        noise_w_scale=args.noise_w_scale,
        rvc_model=args.rvc_model,
        rvc_index=args.rvc_index,
        f0method=args.f0method,
        f0up_key=args.f0up_key,
    )

    if args.output:
        with open(args.output, "wb") as f:
            f.write(wav_bytes)
    else:
        # Emit base64 to stdout
        sys.stdout.write(base64.b64encode(wav_bytes).decode("ascii"))


if __name__ == "__main__":
    main()
