import time
import os
import sys
import wave
import psutil

# Patch torch.load for PyTorch 2.6+ fairseq compatibility
import torch
_orig_torch_load = torch.load
def _safe_torch_load(*args, **kwargs):
    if "weights_only" not in kwargs:
        kwargs["weights_only"] = False
    return _orig_torch_load(*args, **kwargs)
torch.load = _safe_torch_load

from rvc_python.infer import RVCInference

def get_process_memory_mb():
    process = psutil.Process(os.getpid())
    return process.memory_info().rss / (1024 * 1024)

def run_rvc_benchmark():
    model_dir = os.path.abspath("engines/voice_eval/models/teto_utau/Teto-UTAU-Remake")
    pth_file = os.path.join(model_dir, "Teto-UTAU-Remake.pth")
    index_file = os.path.join(model_dir, "added_IVF718_Flat_nprobe_1_Teto-UTAU-Remake_v2.index")
    samples_dir = os.path.abspath("engines/voice_eval/samples")
    
    short_input = os.path.join(samples_dir, "piper_short.wav")
    long_input = os.path.join(samples_dir, "piper_long.wav")

    print("=" * 65)
    print("APPLIO / RVC CPU BENCHMARK — Kasane Teto (UTAU v2)")
    print(f"Python: {sys.version}")
    print(f"PyTorch: {torch.__version__} (CPU: {torch.get_num_threads()} threads)")
    print(f"Model: {pth_file}")
    print(f"Index: {index_file}")
    print(f"Initial Memory RSS: {get_process_memory_mb():.2f} MB")
    print("=" * 65)

    if not os.path.exists(pth_file):
        print(f"Error: Model not found at {pth_file}")
        return

    # 1. Initialize RVC Inference Engine on CPU
    init_start = time.perf_counter()
    rvc = RVCInference(
        device="cpu:0",
        model_path=pth_file,
        index_path=index_file,
        version="v2"
    )
    init_duration_ms = (time.perf_counter() - init_start) * 1000
    post_init_mem = get_process_memory_mb()
    print(f"\nRVC Engine initialized in {init_duration_ms:.2f} ms")
    print(f"Memory after engine init: {post_init_mem:.2f} MB")

    def get_audio_duration(path):
        with wave.open(path, "rb") as wf:
            return wf.getnframes() / float(wf.getframerate())

    short_duration_s = get_audio_duration(short_input)
    long_duration_s = get_audio_duration(long_input)

    benchmark_runs = [
        # (name, input_file, input_duration, f0method, f0up_key, index_rate)
        ("Short Sentence (PM Pitch)", short_input, short_duration_s, "pm", 0, 0.75),
        ("Short Sentence (RMVPE Pitch)", short_input, short_duration_s, "rmvpe", 0, 0.75),
        ("Long Paragraph (PM Pitch)", long_input, long_duration_s, "pm", 0, 0.75),
        ("Long Paragraph (RMVPE Pitch)", long_input, long_duration_s, "rmvpe", 0, 0.75),
    ]

    results = []

    for name, in_wav, in_dur, f0method, f0up_key, index_rate in benchmark_runs:
        out_wav = os.path.join(samples_dir, f"teto_converted_{f0method}_{'short' if 'Short' in name else 'long'}.wav")
        print(f"\n--- Running Test: {name} ---")
        print(f"Input: {in_wav} ({in_dur:.3f} s)")
        print(f"Parameters: f0method={f0method}, f0up_key={f0up_key}, index_rate={index_rate}")

        rvc.set_params(
            f0method=f0method,
            f0up_key=f0up_key,
            index_rate=index_rate,
            filter_radius=3,
            protect=0.33
        )

        mem_before = get_process_memory_mb()
        cpu_before = psutil.cpu_percent(interval=None)
        
        t0 = time.perf_counter()
        rvc.infer_file(in_wav, out_wav)
        conversion_time_s = time.perf_counter() - t0
        
        cpu_after = psutil.cpu_percent(interval=None)
        mem_after = get_process_memory_mb()

        # Check output wav
        with wave.open(out_wav, "rb") as wf:
            out_sr = wf.getframerate()
            out_channels = wf.getnchannels()
            out_dur_s = wf.getnframes() / float(out_sr)

        rtf = conversion_time_s / in_dur if in_dur > 0 else 0
        speedup = 1.0 / rtf if rtf > 0 else 0

        res = {
            "name": name,
            "f0method": f0method,
            "in_dur_s": round(in_dur, 3),
            "out_dur_s": round(out_dur_s, 3),
            "conv_time_s": round(conversion_time_s, 3),
            "conv_time_ms": round(conversion_time_s * 1000, 2),
            "rtf": round(rtf, 4),
            "speedup": round(speedup, 2),
            "out_sr": out_sr,
            "mem_rss_mb": round(mem_after, 2),
            "output_file": out_wav
        }
        results.append(res)

        print(f"Conversion Time: {conversion_time_s:.3f} s ({conversion_time_s * 1000:.1f} ms)")
        print(f"Real-Time Factor (RTF): {rtf:.4f} ({'Slower' if rtf > 1 else 'Faster'} than real-time: {speedup:.2f}x)")
        print(f"Output Sample Rate: {out_sr} Hz, Duration: {out_dur_s:.3f} s")
        print(f"Memory RSS: {mem_after:.2f} MB (Delta: {mem_after - mem_before:+.2f} MB)")
        print(f"Saved: {out_wav}")

    # Phase 2.1D: Reliability and Edge Cases
    print("\n" + "=" * 65)
    print("PHASE 2.1D: RELIABILITY, ERROR HANDLING & REPEATED SYNTHESIS")
    print("=" * 65)

    # 1. Missing model error test
    print("\n1. Missing model error handling:")
    try:
        dummy_rvc = RVCInference(device="cpu:0")
        dummy_rvc.load_model("engines/voice_eval/models/non_existent.pth")
        print("FAIL: Expected ValueError for missing model, but none was raised.")
    except Exception as e:
        print(f"PASS: Handled missing model gracefully ({type(e).__name__}: {e})")

    # 2. Invalid audio input
    print("\n2. Invalid audio input handling:")
    invalid_path = os.path.join(samples_dir, "corrupt.wav")
    with open(invalid_path, "wb") as f:
        f.write(b"not a real wav file")
    try:
        rvc.infer_file(invalid_path, os.path.join(samples_dir, "corrupt_out.wav"))
        print("FAIL: Expected exception for corrupt audio, but none was raised.")
    except Exception as e:
        print(f"PASS: Handled corrupt audio gracefully ({type(e).__name__}: {e})")
    finally:
        if os.path.exists(invalid_path):
            os.remove(invalid_path)

    # 3. Repeated synthesis memory stability test (3 runs)
    print("\n3. Repeated synthesis memory stability (3 runs with pm):")
    rvc.set_params(f0method="pm")
    rep_times = []
    mem_readings = []
    for i in range(3):
        t_rep = time.perf_counter()
        tmp_out = os.path.join(samples_dir, f"teto_rep_{i}.wav")
        rvc.infer_file(short_input, tmp_out)
        dur = time.perf_counter() - t_rep
        rep_times.append(dur)
        mem_readings.append(get_process_memory_mb())
        print(f" Run {i+1}: {dur:.3f} s, Memory RSS: {mem_readings[-1]:.2f} MB")
        if os.path.exists(tmp_out):
            os.remove(tmp_out)

    print(f"Average repeated conversion latency: {sum(rep_times)/len(rep_times):.3f} s")
    print(f"Memory growth across runs: {mem_readings[-1] - mem_readings[0]:+.2f} MB")

    # 4. Model unloading test
    print("\n4. Model unloading test:")
    mem_before_unload = get_process_memory_mb()
    rvc.unload_model()
    mem_after_unload = get_process_memory_mb()
    print(f"Memory before unload: {mem_before_unload:.2f} MB -> after unload: {mem_after_unload:.2f} MB")

    # Summary table
    print("\n" + "=" * 65)
    print("RVC CPU BENCHMARK SUMMARY")
    print(f"{'Test':<30} | {'Audio Dur':<10} | {'Conv Time':<10} | {'RTF':<8} | {'Speed':<8}")
    print("-" * 65)
    for r in results:
        print(f"{r['name']:<30} | {r['in_dur_s']:>8.3f} s | {r['conv_time_s']:>8.3f} s | {r['rtf']:>8.4f} | {r['speedup']:>6.2f}x")
    print("=" * 65)

if __name__ == "__main__":
    run_rvc_benchmark()
