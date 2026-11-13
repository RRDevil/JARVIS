import time
import os
import sys
import psutil
import threading
import queue
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

def run_preloading_benchmark():
    print("=" * 70)
    print("MILESTONE 2.2 — BENCHMARK 1: MODEL PRELOADING & CONCURRENCY")
    print(f"Python: {sys.version.split()[0]} on {sys.platform}")
    print(f"Logical CPUs: {psutil.cpu_count(logical=True)} ({psutil.cpu_count(logical=False)} physical)")
    print(f"PyTorch: {torch.__version__} (Threads: {torch.get_num_threads()})")
    print("=" * 70)

    model_dir = os.path.abspath("engines/voice_eval/models/teto_utau/Teto-UTAU-Remake")
    pth_file = os.path.join(model_dir, "Teto-UTAU-Remake.pth")
    index_file = os.path.join(model_dir, "added_IVF718_Flat_nprobe_1_Teto-UTAU-Remake_v2.index")
    piper_onnx = os.path.abspath("engines/voice_eval/models/en_US-lessac-medium.onnx")

    idle_mem = get_process_memory_mb()
    print(f"Baseline Idle Memory (Process RSS): {idle_mem:.2f} MB")

    # 1. Measure Piper load time & memory
    t0 = time.perf_counter()
    piper_voice = PiperVoice.load(piper_onnx)
    piper_load_time_ms = (time.perf_counter() - t0) * 1000
    piper_loaded_mem = get_process_memory_mb()
    print(f"\n[1] Piper Voice Load: {piper_load_time_ms:.2f} ms")
    print(f"    Memory RSS after Piper: {piper_loaded_mem:.2f} MB (+{piper_loaded_mem - idle_mem:.2f} MB)")

    # 2. Measure Cold RVC load time & memory
    cpu_monitor_stop = threading.Event()
    cpu_load_readings = []

    def monitor_cpu():
        p = psutil.Process(os.getpid())
        while not cpu_monitor_stop.is_set():
            try:
                cpu_load_readings.append(p.cpu_percent(interval=0.05))
            except Exception:
                break

    cpu_thread = threading.Thread(target=monitor_cpu, daemon=True)
    cpu_thread.start()

    t1 = time.perf_counter()
    rvc = RVCInference(
        device="cpu:0",
        model_path=pth_file,
        index_path=index_file,
        version="v2"
    )
    rvc_cold_load_ms = (time.perf_counter() - t1) * 1000
    cpu_monitor_stop.set()
    cpu_thread.join()

    rvc_loaded_mem = get_process_memory_mb()
    peak_cpu = max(cpu_load_readings) if cpu_load_readings else 0
    avg_cpu = sum(cpu_load_readings) / len(cpu_load_readings) if cpu_load_readings else 0

    print(f"\n[2] Cold RVC Model Load: {rvc_cold_load_ms:.2f} ms ({rvc_cold_load_ms/1000:.2f} s)")
    print(f"    Memory RSS after RVC: {rvc_loaded_mem:.2f} MB (+{rvc_loaded_mem - piper_loaded_mem:.2f} MB)")
    print(f"    CPU Usage during load: Avg {avg_cpu:.1f}%, Peak {peak_cpu:.1f}%")

    # 3. Model Unload & Warm Reload
    rvc.unload_model()
    unloaded_mem = get_process_memory_mb()
    print(f"\n[3] Memory after RVC unload: {unloaded_mem:.2f} MB (-{rvc_loaded_mem - unloaded_mem:.2f} MB)")

    t2 = time.perf_counter()
    rvc.load_model(pth_file)
    rvc_warm_load_ms = (time.perf_counter() - t2) * 1000
    warm_mem = get_process_memory_mb()
    print(f"    Warm RVC Model Reload: {rvc_warm_load_ms:.2f} ms")
    print(f"    Memory RSS after warm reload: {warm_mem:.2f} MB")

    # 4. Concurrency Test: Simulate Gemini Response Generation while Preloading
    print("\n[4] Concurrency Test: Simulated Gemini Stream + Concurrent Model Preload")
    # Simulate Gemini streaming 25 tokens (average short sentence, ~60 words/sec, chunked every 40ms)
    def simulate_gemini_stream(output_queue, cancel_event):
        chunks = [
            "Good ", "evening, ", "Sir. ", "All ", "holographic ", "systems ", "are ", 
            "operational ", "and ", "diagnostic ", "routines ", "indicate ", "optimal ", 
            "throughput. ", "Local ", "memory ", "allocations ", "remain ", "safe, ", 
            "and ", "background ", "services ", "are ", "synchronized. "
        ]
        start_time = time.perf_counter()
        latencies = []
        for chunk in chunks:
            if cancel_event.is_set():
                break
            chunk_t0 = time.perf_counter()
            time.sleep(0.04)  # 40ms per token (~25 tok/s realistic Gemini streaming rate)
            elapsed = time.perf_counter() - chunk_t0
            latencies.append(elapsed)
            output_queue.put((chunk, time.perf_counter() - start_time))
        return latencies

    # Run Gemini baseline without background loading
    gem_q_baseline = queue.Queue()
    stop_event = threading.Event()
    t_base_start = time.perf_counter()
    base_latencies = simulate_gemini_stream(gem_q_baseline, stop_event)
    gem_baseline_dur = (time.perf_counter() - t_base_start) * 1000
    print(f"    Baseline Gemini Stream (no load): Total {gem_baseline_dur:.1f} ms, Avg chunk latency {sum(base_latencies)/len(base_latencies)*1000:.1f} ms")

    # Now unload RVC, and run Gemini stream while concurrently reloading RVC + Piper in worker thread
    rvc.unload_model()
    gem_q_concurrent = queue.Queue()
    load_done_event = threading.Event()
    load_time_holder = {}

    def background_loader():
        lt0 = time.perf_counter()
        rvc.load_model(pth_file)
        load_time_holder["rvc_load_ms"] = (time.perf_counter() - lt0) * 1000
        load_done_event.set()

    load_thread = threading.Thread(target=background_loader)
    t_conc_start = time.perf_counter()
    load_thread.start()
    conc_latencies = simulate_gemini_stream(gem_q_concurrent, stop_event)
    load_thread.join()
    gem_concurrent_dur = (time.perf_counter() - t_conc_start) * 1000

    print(f"    Concurrent Gemini Stream (during RVC load): Total {gem_concurrent_dur:.1f} ms, Avg chunk latency {sum(conc_latencies)/len(conc_latencies)*1000:.1f} ms")
    print(f"    Concurrent RVC Load duration: {load_time_holder.get('rvc_load_ms', 0):.1f} ms")
    print(f"    Stream Jitter / Delay added: {gem_concurrent_dur - gem_baseline_dur:+.1f} ms ({(gem_concurrent_dur - gem_baseline_dur)/gem_baseline_dur * 100:+.1f}%)")

    # Check if load finished before or during Gemini stream
    finished_before = load_time_holder.get('rvc_load_ms', 0) < gem_concurrent_dur
    print(f"    Model finished loading {'BEFORE' if finished_before else 'AFTER'} Gemini stream completed!")
    print(f"    Lead time saved for voice synthesis: {min(load_time_holder.get('rvc_load_ms', 0), gem_concurrent_dur):.1f} ms")

    results = {
        "idle_mem_mb": round(idle_mem, 2),
        "piper_load_ms": round(piper_load_time_ms, 2),
        "piper_mem_rss_mb": round(piper_loaded_mem, 2),
        "rvc_cold_load_ms": round(rvc_cold_load_ms, 2),
        "rvc_loaded_mem_mb": round(rvc_loaded_mem, 2),
        "rvc_warm_load_ms": round(rvc_warm_load_ms, 2),
        "rvc_unloaded_mem_mb": round(unloaded_mem, 2),
        "gemini_baseline_stream_ms": round(gem_baseline_dur, 2),
        "gemini_concurrent_stream_ms": round(gem_concurrent_dur, 2),
        "stream_delay_pct": round((gem_concurrent_dur - gem_baseline_dur)/gem_baseline_dur * 100, 2),
        "lead_time_saved_ms": round(min(load_time_holder.get('rvc_load_ms', 0), gem_concurrent_dur), 2)
    }

    out_json = os.path.abspath("engines/voice_eval/preloading_benchmark_results.json")
    with open(out_json, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved benchmark results to {out_json}")

if __name__ == "__main__":
    run_preloading_benchmark()

