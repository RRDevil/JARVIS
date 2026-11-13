import time
import os
import sys
import wave
import psutil
from piper.voice import PiperVoice

def get_process_memory_mb():
    process = psutil.Process(os.getpid())
    return process.memory_info().rss / (1024 * 1024)

def run_piper_benchmark():
    model_path = os.path.abspath("engines/voice_eval/models/en_US-lessac-medium.onnx")
    config_path = os.path.abspath("engines/voice_eval/models/en_US-lessac-medium.onnx.json")
    output_dir = os.path.abspath("engines/voice_eval/samples")
    os.makedirs(output_dir, exist_ok=True)

    if not os.path.exists(model_path):
        print(f"Error: Model not found at {model_path}")
        return

    print("=" * 60)
    print("PIPER TTS CPU BENCHMARK")
    print(f"Python: {sys.version}")
    print(f"Model: {model_path}")
    print(f"Initial Memory RSS: {get_process_memory_mb():.2f} MB")
    print("=" * 60)

    # 1. Load model
    load_start = time.perf_counter()
    voice = PiperVoice.load(model_path, config_path=config_path, use_cuda=False)
    load_time_ms = (time.perf_counter() - load_start) * 1000
    post_load_mem = get_process_memory_mb()
    print(f"Model loaded in {load_time_ms:.2f} ms")
    print(f"Memory after load: {post_load_mem:.2f} MB (Delta: {post_load_mem - get_process_memory_mb():.2f} MB)")

    test_cases = [
        {
            "name": "short_sentence",
            "text": "Good evening, Sir. All holographic systems are operational.",
            "output_file": os.path.join(output_dir, "piper_short.wav"),
        },
        {
            "name": "long_paragraph",
            "text": "Diagnostic routines across the central computational bus indicate optimal throughput. Memory allocations remain within safe boundaries, and no anomalous network traffic has been detected on local ports.",
            "output_file": os.path.join(output_dir, "piper_long.wav"),
        }
    ]

    results = []

    for tc in test_cases:
        text = tc["text"]
        out_path = tc["output_file"]
        print(f"\n--- Running Test: {tc['name']} ---")
        print(f"Text ({len(text.split())} words): '{text}'")

        mem_before = get_process_memory_mb()
        cpu_before = psutil.cpu_percent(interval=None)
        
        t0 = time.perf_counter()
        with wave.open(out_path, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(voice.config.sample_rate)
            for chunk in voice.synthesize(text):
                wav_file.writeframes(chunk.audio_int16_bytes)
        synth_duration_s = time.perf_counter() - t0
        
        cpu_after = psutil.cpu_percent(interval=None)
        mem_after = get_process_memory_mb()

        # Read back wav to verify length and sample rate
        with wave.open(out_path, "rb") as wf:
            sample_rate = wf.getframerate()
            num_channels = wf.getnchannels()
            num_frames = wf.getnframes()
            sample_width = wf.getsampwidth()
            audio_duration_s = num_frames / float(sample_rate)

        rtf = synth_duration_s / audio_duration_s if audio_duration_s > 0 else 0

        res = {
            "name": tc["name"],
            "word_count": len(text.split()),
            "audio_duration_s": round(audio_duration_s, 3),
            "synth_duration_ms": round(synth_duration_s * 1000, 2),
            "rtf": round(rtf, 4),
            "speedup": round(1.0 / rtf, 2) if rtf > 0 else 0,
            "sample_rate": sample_rate,
            "channels": num_channels,
            "sample_width_bytes": sample_width,
            "mem_rss_mb": round(mem_after, 2),
            "output_file": out_path
        }
        results.append(res)

        print(f"Audio Duration: {audio_duration_s:.3f} s")
        print(f"Synthesis Time: {synth_duration_s * 1000:.2f} ms")
        print(f"Real-Time Factor (RTF): {rtf:.4f} (Speed: {res['speedup']}x real-time)")
        print(f"Sample Rate: {sample_rate} Hz, Channels: {num_channels}, Bit Depth: {sample_width * 8}-bit")
        print(f"Memory RSS: {mem_after:.2f} MB")
        print(f"Output saved to: {out_path}")

    # Test repeated synthesis stability
    print("\n--- Running Repeated Synthesis Test (5 iterations) ---")
    latencies = []
    for i in range(5):
        t_start = time.perf_counter()
        with wave.open(os.path.join(output_dir, f"piper_repeat_{i}.wav"), "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(voice.config.sample_rate)
            for chunk in voice.synthesize("System check normal."):
                wav_file.writeframes(chunk.audio_int16_bytes)
        lat = (time.perf_counter() - t_start) * 1000
        latencies.append(lat)
        print(f" Iteration {i+1}: {lat:.2f} ms")
    
    avg_lat = sum(latencies) / len(latencies)
    print(f"Average latency for short phrase: {avg_lat:.2f} ms")

    print("\n" + "=" * 60)
    print("PIPER BENCHMARK SUMMARY")
    for r in results:
        print(f"- {r['name']}: {r['audio_duration_s']}s audio synthesized in {r['synth_duration_ms']}ms (RTF: {r['rtf']}, {r['speedup']}x real-time)")
    print(f"- Peak Memory RSS: {get_process_memory_mb():.2f} MB")
    print("=" * 60)

if __name__ == "__main__":
    run_piper_benchmark()
