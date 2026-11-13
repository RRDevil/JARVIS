import time
import os
import sys
import wave
import psutil
import json

# Patch torch.load for PyTorch 2.6+ fairseq compatibility
import torch
_orig_torch_load = torch.load
def _safe_torch_load(*args, **kwargs):
    if "weights_only" not in kwargs:
        kwargs["weights_only"] = False
    return _orig_torch_load(*args, **kwargs)
torch.load = _safe_torch_load

from rvc_python.infer import RVCInference
from piper import PiperVoice

def get_process_memory_mb():
    process = psutil.Process(os.getpid())
    return process.memory_info().rss / (1024 * 1024)

def get_audio_duration(path):
    with wave.open(path, "rb") as wf:
        return wf.getnframes() / float(wf.getframerate())

def run_full_response_benchmark():
    print("=" * 75)
    print("MILESTONE 2.2 — BENCHMARK 2: ASYNCHRONOUS FULL-RESPONSE PIPELINE")
    print(f"Machine: Intel Core i7-1355U (12 threads), Windows 11")
    print(f"PyTorch: {torch.__version__} (Threads: {torch.get_num_threads()})")
    print("=" * 75)

    samples_dir = os.path.abspath("engines/voice_eval/samples")
    os.makedirs(samples_dir, exist_ok=True)

    model_dir = os.path.abspath("engines/voice_eval/models/teto_utau/Teto-UTAU-Remake")
    pth_file = os.path.join(model_dir, "Teto-UTAU-Remake.pth")
    index_file = os.path.join(model_dir, "added_IVF718_Flat_nprobe_1_Teto-UTAU-Remake_v2.index")
    piper_onnx = os.path.abspath("engines/voice_eval/models/en_US-lessac-medium.onnx")

    test_utterances = [
        {
            "id": "short",
            "name": "Short Utterance (8 words)",
            "text": "Good evening, Sir. All holographic systems are operational."
        },
        {
            "id": "medium",
            "name": "Medium Utterance (18 words)",
            "text": "All background diagnostic services report nominal performance. The local database has been synchronized, and network latency is minimal."
        },
        {
            "id": "long",
            "name": "Long Utterance (35 words)",
            "text": "Diagnostic routines across the central computational bus indicate optimal throughput. Memory allocations remain within safe boundaries, and no anomalous network traffic has been detected on local ports."
        }
    ]

    # Pre-load Piper
    print("\nInitializing Piper TTS engine...")
    t_piper_load = time.perf_counter()
    voice = PiperVoice.load(piper_onnx)
    piper_load_ms = (time.perf_counter() - t_piper_load) * 1000
    print(f"Piper loaded in {piper_load_ms:.1f} ms")

    # Step 1: Synthesize all 3 baseline Piper audios
    print("\n--- [Step 1] Synthesizing Piper TTS Audio Inputs ---")
    piper_results = {}
    for utt in test_utterances:
        out_wav = os.path.join(samples_dir, f"async_piper_{utt['id']}.wav")
        t0 = time.perf_counter()
        with wave.open(out_wav, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(voice.config.sample_rate)
            for chunk in voice.synthesize(utt["text"]):
                wf.writeframes(chunk.audio_int16_bytes)
        synth_time_s = time.perf_counter() - t0
        audio_dur = get_audio_duration(out_wav)
        piper_results[utt["id"]] = {
            "wav_path": out_wav,
            "audio_dur_s": round(audio_dur, 3),
            "synth_time_s": round(synth_time_s, 4),
            "synth_time_ms": round(synth_time_s * 1000, 1),
            "rtf": round(synth_time_s / audio_dur, 4)
        }
        print(f"[{utt['id'].upper()}] Audio: {audio_dur:.2f} s | Piper Synth Time: {synth_time_s*1000:.1f} ms | RTF: {synth_time_s / audio_dur:.4f}")

    # Step 2: Initialize RVC
    print("\n--- [Step 2] Initializing RVC Engine (Cold Load) ---")
    t_rvc_load = time.perf_counter()
    rvc = RVCInference(
        device="cpu:0",
        model_path=pth_file,
        index_path=index_file,
        version="v2"
    )
    rvc_load_time_ms = (time.perf_counter() - t_rvc_load) * 1000
    print(f"RVC Engine initialized in {rvc_load_time_ms:.1f} ms (RSS: {get_process_memory_mb():.1f} MB)")

    # Step 3: Run Full Response Conversions across Short, Medium, Long with PM and RMVPE
    benchmarks = []

    # Test matrix:
    # 1. Short (PM) - Warm
    # 2. Short (RMVPE) - Warm
    # 3. Medium (PM) - Warm
    # 4. Medium (RMVPE) - Warm
    # 5. Long (PM) - Warm
    # 6. Long (RMVPE) - Warm
    matrix = [
        ("short", "pm"),
        ("short", "rmvpe"),
        ("medium", "pm"),
        ("medium", "rmvpe"),
        ("long", "pm"),
        ("long", "rmvpe"),
    ]

    print("\n--- [Step 3] Running Asynchronous Full-Response RVC Conversions ---")
    for utt_id, f0method in matrix:
        utt_meta = next(u for u in test_utterances if u["id"] == utt_id)
        piper_meta = piper_results[utt_id]
        in_wav = piper_meta["wav_path"]
        in_dur = piper_meta["audio_dur_s"]
        out_wav = os.path.join(samples_dir, f"async_teto_{utt_id}_{f0method}.wav")

        rvc.set_params(
            f0method=f0method,
            f0up_key=0,
            index_rate=0.75,
            filter_radius=3,
            protect=0.33
        )

        # Baseline CPU and Mem
        mem_before = get_process_memory_mb()
        p = psutil.Process(os.getpid())
        p.cpu_percent(interval=None)

        t_start = time.perf_counter()
        rvc.infer_file(in_wav, out_wav)
        conversion_time_s = time.perf_counter() - t_start

        cpu_used = p.cpu_percent(interval=None)
        mem_after = get_process_memory_mb()
        out_dur = get_audio_duration(out_wav)

        total_prep_time_s = piper_meta["synth_time_s"] + conversion_time_s
        rtf = conversion_time_s / in_dur

        entry = {
            "utt_id": utt_id,
            "name": utt_meta["name"],
            "f0method": f0method,
            "text": utt_meta["text"],
            "audio_dur_s": round(out_dur, 3),
            "piper_synth_time_s": piper_meta["synth_time_s"],
            "rvc_conv_time_s": round(conversion_time_s, 3),
            "total_prep_time_s": round(total_prep_time_s, 3),
            "rtf": round(rtf, 4),
            "speedup": round(1.0 / rtf, 2) if rtf > 0 else 0,
            "cpu_percent": round(cpu_used, 1),
            "mem_rss_mb": round(mem_after, 1),
            "output_wav": out_wav
        }
        benchmarks.append(entry)

        print(f"\n>> {utt_meta['name']} | Method: {f0method.upper()}")
        print(f"   Audio Duration: {out_dur:.2f} s")
        print(f"   Piper Synth:    {piper_meta['synth_time_s']*1000:.1f} ms")
        print(f"   RVC Conversion: {conversion_time_s:.2f} s")
        print(f"   Total Lead Time Before Playback: {total_prep_time_s:.2f} s")
        print(f"   Real-Time Factor: {rtf:.2f}x ({'Slower' if rtf > 1 else 'Faster'} than realtime)")
        print(f"   Process Peak RAM: {mem_after:.1f} MB (CPU: {cpu_used:.1f}%)")

    # Step 4: Compare Cold vs Warm Start for Short Utterance
    print("\n--- [Step 4] Cold vs Warm Comparison (Short Utterance, PM) ---")
    cold_total_prep_s = (piper_load_ms / 1000) + (rvc_load_time_ms / 1000) + benchmarks[0]["total_prep_time_s"]
    warm_total_prep_s = benchmarks[0]["total_prep_time_s"]
    print(f"Cold Total (Including Engine Inits): {cold_total_prep_s:.2f} s")
    print(f"Warm Total (Preloaded In-Memory):   {warm_total_prep_s:.2f} s")
    print(f"Preloading Latency Benefit:         {cold_total_prep_s - warm_total_prep_s:.2f} s saved")

    output_summary = {
        "piper_load_time_ms": round(piper_load_ms, 1),
        "rvc_cold_load_time_ms": round(rvc_load_time_ms, 1),
        "piper_baselines": piper_results,
        "benchmarks": benchmarks,
        "cold_vs_warm": {
            "short_pm_cold_s": round(cold_total_prep_s, 2),
            "short_pm_warm_s": round(warm_total_prep_s, 2),
            "latency_saved_s": round(cold_total_prep_s - warm_total_prep_s, 2)
        }
    }

    out_file = os.path.abspath("engines/voice_eval/full_response_benchmark_results.json")
    with open(out_file, "w") as f:
        json.dump(output_summary, f, indent=2)
    print(f"\nAll benchmark results exported to {out_file}")

if __name__ == "__main__":
    run_full_response_benchmark()
