import os
import sys
import time
import json
import psutil
import re
from pathlib import Path

# Add backend to sys.path so app config is available
sys.path.insert(0, os.path.abspath("backend"))

from faster_whisper import WhisperModel

DATASET_MANIFEST = os.path.abspath("engines/voice_eval/stt/dataset/manifest.json")
MODELS_DIR = os.path.abspath("data/models/stt")
RESULTS_DIR = os.path.abspath("engines/voice_eval/stt/results")
os.makedirs(RESULTS_DIR, exist_ok=True)

def get_process_memory_mb():
    process = psutil.Process(os.getpid())
    return process.memory_info().rss / (1024 * 1024)

def normalize_text(text: str) -> str:
    """Normalize text for fair WER/CER comparison: lowercase, remove punctuation, collapse whitespace."""
    text = text.lower()
    # Normalize common abbreviations
    text = text.replace("j.a.r.v.i.s.", "jarvis")
    text = text.replace("jarvis", "jarvis")
    text = re.sub(r"[^\w\s]", " ", text)
    return " ".join(text.split())

def compute_levenshtein(seq1, seq2):
    """Standard dynamic programming Levenshtein distance."""
    d = [[0] * (len(seq2) + 1) for _ in range(len(seq1) + 1)]
    for i in range(len(seq1) + 1):
        d[i][0] = i
    for j in range(len(seq2) + 1):
        d[0][j] = j
    for i in range(1, len(seq1) + 1):
        for j in range(1, len(seq2) + 1):
            cost = 0 if seq1[i - 1] == seq2[j - 1] else 1
            d[i][j] = min(
                d[i - 1][j] + 1,      # deletion
                d[i][j - 1] + 1,      # insertion
                d[i - 1][j - 1] + cost # substitution
            )
    return d[len(seq1)][len(seq2)]

def compute_wer(reference: str, hypothesis: str) -> float:
    ref_words = normalize_text(reference).split()
    hyp_words = normalize_text(hypothesis).split()
    if not ref_words:
        return 0.0 if not hyp_words else 1.0
    edit_dist = compute_levenshtein(ref_words, hyp_words)
    return round(edit_dist / len(ref_words), 4)

def compute_cer(reference: str, hypothesis: str) -> float:
    ref_chars = list(normalize_text(reference).replace(" ", ""))
    hyp_chars = list(normalize_text(hypothesis).replace(" ", ""))
    if not ref_chars:
        return 0.0 if not hyp_chars else 1.0
    edit_dist = compute_levenshtein(ref_chars, hyp_chars)
    return round(edit_dist / len(ref_chars), 4)

# Test Prompts
PROMPT_STATIC_NOUNS = (
    "J.A.R.V.I.S., JARVIS, Notepad, Calculator, Chrome, taskbar, desktop, terminal, "
    "PowerShell, Python, Explorer, maximize, minimize, screenshot, OCR, settings"
)

PROMPT_CONVERSATIONAL = (
    "I am J.A.R.V.I.S., your desktop AI assistant. Sir, please open Notepad, Calculator, "
    "Google Chrome, PowerShell, Python, terminal, File Explorer, settings, or take a screenshot."
)

CONFIGURATIONS = [
    {
        "name": "Config A: tiny.en (Baseline Baseline)",
        "model_size": "tiny.en",
        "beam_size": 1,
        "initial_prompt": PROMPT_STATIC_NOUNS,
        "condition_on_previous_text": True,
        "vad_filter": True,
        "vad_parameters": dict(min_silence_duration_ms=800, speech_pad_ms=300),
    },
    {
        "name": "Config B: base.en (Current Production)",
        "model_size": "base.en",
        "beam_size": 1,
        "initial_prompt": PROMPT_STATIC_NOUNS,
        "condition_on_previous_text": True,
        "vad_filter": True,
        "vad_parameters": dict(min_silence_duration_ms=800, speech_pad_ms=300),
    },
    {
        "name": "Config C: base.en + Conversational Prompt + No Condition",
        "model_size": "base.en",
        "beam_size": 1,
        "initial_prompt": PROMPT_CONVERSATIONAL,
        "condition_on_previous_text": False,
        "vad_filter": True,
        "vad_parameters": dict(min_silence_duration_ms=800, speech_pad_ms=300),
    },
    {
        "name": "Config D: base.en + Beam=2 + Tuned VAD (Candidate Best)",
        "model_size": "base.en",
        "beam_size": 2,
        "initial_prompt": PROMPT_CONVERSATIONAL,
        "condition_on_previous_text": False,
        "vad_filter": True,
        "vad_parameters": dict(threshold=0.35, min_speech_duration_ms=150, min_silence_duration_ms=800, speech_pad_ms=400),
    },
    {
        "name": "Config E: base.en + Beam=5 (High Accuracy Baseline)",
        "model_size": "base.en",
        "beam_size": 5,
        "initial_prompt": PROMPT_CONVERSATIONAL,
        "condition_on_previous_text": False,
        "vad_filter": True,
        "vad_parameters": dict(threshold=0.35, min_speech_duration_ms=150, min_silence_duration_ms=800, speech_pad_ms=400),
    },
    {
        "name": "Config F: small.en + Beam=1 (Heavyweight Exploration)",
        "model_size": "small.en",
        "beam_size": 1,
        "initial_prompt": PROMPT_CONVERSATIONAL,
        "condition_on_previous_text": False,
        "vad_filter": True,
        "vad_parameters": dict(threshold=0.35, min_speech_duration_ms=150, min_silence_duration_ms=800, speech_pad_ms=400),
    }
]

def run_benchmark():
    with open(DATASET_MANIFEST, "r", encoding="utf-8") as f:
        dataset = json.load(f)

    print("=" * 70)
    print("J.A.R.V.I.S. STT ACCURACY & LATENCY BENCHMARK SUITE")
    print(f"Dataset: {len(dataset)} verified test cases")
    print(f"CPU: {psutil.cpu_count(logical=False)} Physical / {psutil.cpu_count(logical=True)} Logical Cores")
    print(f"Initial Memory RSS: {get_process_memory_mb():.2f} MB")
    print("=" * 70)

    summary_results = []

    # Cache loaded models so we only load each size once
    loaded_models = {}

    for cfg in CONFIGURATIONS:
        cfg_name = cfg["name"]
        model_size = cfg["model_size"]
        print(f"\n>>> Running Benchmark: {cfg_name} <<<")

        # Load or reuse model
        if model_size not in loaded_models:
            print(f"Loading Whisper model '{model_size}' (int8 cpu)...")
            t_load = time.perf_counter()
            loaded_models[model_size] = WhisperModel(
                model_size,
                device="cpu",
                compute_type="int8",
                download_root=MODELS_DIR,
            )
            load_time_ms = (time.perf_counter() - t_load) * 1000
            print(f"Loaded '{model_size}' in {load_time_ms:.1f} ms. RSS: {get_process_memory_mb():.2f} MB")

        model = loaded_models[model_size]

        case_results = []
        total_audio_dur = 0.0
        total_latency_s = 0.0
        exact_matches = 0
        short_cmd_count = 0
        empty_count = 0

        for item in dataset:
            wav_path = item["file"]
            ref_text = item["reference"]
            cat = item["category"]

            t0 = time.perf_counter()
            segments, info = model.transcribe(
                wav_path,
                beam_size=cfg["beam_size"],
                language="en",
                initial_prompt=cfg["initial_prompt"],
                condition_on_previous_text=cfg["condition_on_previous_text"],
                vad_filter=cfg["vad_filter"],
                vad_parameters=cfg.get("vad_parameters"),
            )

            parts = [s.text.strip() for s in segments if s.text.strip()]
            hyp_text = " ".join(parts).strip()
            elapsed_s = time.perf_counter() - t0

            # Compute error rates
            wer = compute_wer(ref_text, hyp_text)
            cer = compute_cer(ref_text, hyp_text)

            is_exact = normalize_text(ref_text) == normalize_text(hyp_text)
            if cat == "short_command":
                short_cmd_count += 1
                if is_exact:
                    exact_matches += 1

            if not hyp_text:
                empty_count += 1

            dur = item["duration_s"]
            rtf = elapsed_s / dur if dur > 0 else 0
            total_audio_dur += dur
            total_latency_s += elapsed_s

            case_results.append({
                "id": item["id"],
                "category": cat,
                "reference": ref_text,
                "hypothesis": hyp_text,
                "wer": wer,
                "cer": cer,
                "exact_match": is_exact,
                "latency_ms": round(elapsed_s * 1000, 1),
                "rtf": round(rtf, 4)
            })

        avg_wer = sum(r["wer"] for r in case_results) / len(case_results)
        avg_cer = sum(r["cer"] for r in case_results) / len(case_results)
        macro_rtf = total_latency_s / total_audio_dur if total_audio_dur > 0 else 0
        cmd_accuracy = (exact_matches / short_cmd_count) * 100 if short_cmd_count > 0 else 0
        empty_rate = (empty_count / len(case_results)) * 100
        mem_rss = get_process_memory_mb()

        print(f"Results for {cfg_name}:")
        print(f" - Average WER: {avg_wer * 100:.2f}%")
        print(f" - Average CER: {avg_cer * 100:.2f}%")
        print(f" - Short Command Exact Match: {cmd_accuracy:.1f}% ({exact_matches}/{short_cmd_count})")
        print(f" - Average RTF: {macro_rtf:.4f} ({1.0/macro_rtf:.2f}x real-time speed)")
        print(f" - Total Processing Time: {total_latency_s:.2f} s for {total_audio_dur:.2f} s audio")
        print(f" - Empty Transcript Rate: {empty_rate:.1f}%")
        print(f" - Memory RSS: {mem_rss:.2f} MB")

        summary_results.append({
            "config": cfg_name,
            "model_size": model_size,
            "beam_size": cfg["beam_size"],
            "avg_wer_pct": round(avg_wer * 100, 2),
            "avg_cer_pct": round(avg_cer * 100, 2),
            "cmd_exact_match_pct": round(cmd_accuracy, 1),
            "macro_rtf": round(macro_rtf, 4),
            "speedup": round(1.0 / macro_rtf, 2) if macro_rtf > 0 else 0,
            "avg_latency_ms": round((total_latency_s / len(case_results)) * 1000, 1),
            "empty_rate_pct": round(empty_rate, 1),
            "memory_rss_mb": round(mem_rss, 1),
            "details": case_results
        })

    # Save detailed benchmark output
    results_path = os.path.join(RESULTS_DIR, "stt_benchmark_results.json")
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump(summary_results, f, indent=2)

    # Print markdown comparison table
    print("\n" + "=" * 90)
    print("STT BENCHMARK COMPARISON TABLE")
    print(f"{'Configuration':<42} | {'WER (%)':<8} | {'CER (%)':<8} | {'Cmd Acc':<8} | {'Avg Lat':<9} | {'RTF':<7} | {'Speed':<6} | {'RAM':<8}")
    print("-" * 90)
    for s in summary_results:
        print(f"{s['config']:<42} | {s['avg_wer_pct']:>6.2f}% | {s['avg_cer_pct']:>6.2f}% | {s['cmd_exact_match_pct']:>6.1f}% | {s['avg_latency_ms']:>7.1f}ms | {s['macro_rtf']:>6.4f} | {s['speedup']:>5.1f}x | {s['memory_rss_mb']:>6.1f}MB")
    print("=" * 90)

if __name__ == "__main__":
    run_benchmark()

