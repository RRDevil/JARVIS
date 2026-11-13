import os
import json
import wave
import struct
import math
import random
import win32com.client

DATASET_DIR = os.path.abspath("engines/voice_eval/stt/dataset")
os.makedirs(DATASET_DIR, exist_ok=True)

# 16 Benchmark Test Cases covering all requested scenarios
BENCHMARK_CASES = [
    # Category 1: Short Voice Commands (Exact Match critical)
    {
        "id": "cmd_01_notepad",
        "category": "short_command",
        "reference": "Open Notepad",
        "rate": 0,  # SAPI rate: -10 to 10 (0 is normal)
        "voice_gender": "male",
        "noise_db": None,
        "pause_s": 0.0,
    },
    {
        "id": "cmd_02_calculator",
        "category": "short_command",
        "reference": "Launch Calculator",
        "rate": 0,
        "voice_gender": "female",
        "noise_db": None,
        "pause_s": 0.0,
    },
    {
        "id": "cmd_03_chrome",
        "category": "short_command",
        "reference": "Open Google Chrome",
        "rate": 0,
        "voice_gender": "male",
        "noise_db": None,
        "pause_s": 0.0,
    },
    {
        "id": "cmd_04_screenshot",
        "category": "short_command",
        "reference": "Take a screenshot",
        "rate": 0,
        "voice_gender": "female",
        "noise_db": None,
        "pause_s": 0.0,
    },

    # Category 2: Conversational Sentences
    {
        "id": "conv_01_status",
        "category": "conversational",
        "reference": "Hello JARVIS can you check the system memory and CPU utilization",
        "rate": 0,
        "voice_gender": "male",
        "noise_db": None,
        "pause_s": 0.0,
    },
    {
        "id": "conv_02_script",
        "category": "conversational",
        "reference": "Please create a new Python script on my desktop and format it cleanly",
        "rate": 0,
        "voice_gender": "female",
        "noise_db": None,
        "pause_s": 0.0,
    },
    {
        "id": "conv_03_meeting",
        "category": "conversational",
        "reference": "What time is the team planning meeting scheduled for this afternoon",
        "rate": 0,
        "voice_gender": "male",
        "noise_db": None,
        "pause_s": 0.0,
    },

    # Category 3: Long Sentences
    {
        "id": "long_01_diagnostic",
        "category": "long_sentence",
        "reference": "Diagnostic routines across the central computational bus indicate optimal throughput and memory allocations remain within safe boundaries",
        "rate": 0,
        "voice_gender": "male",
        "noise_db": None,
        "pause_s": 0.0,
    },
    {
        "id": "long_02_workflow",
        "category": "long_sentence",
        "reference": "I need you to open the project folder in File Explorer inspect the git status of the repository and run all unit tests",
        "rate": 0,
        "voice_gender": "female",
        "noise_db": None,
        "pause_s": 0.0,
    },

    # Category 4: Different Speaking Speeds
    {
        "id": "speed_01_fast",
        "category": "fast_speech",
        "reference": "Minimize all windows immediately and show me the active processes in PowerShell",
        "rate": 4,  # Fast (+4)
        "voice_gender": "male",
        "noise_db": None,
        "pause_s": 0.0,
    },
    {
        "id": "speed_02_slow",
        "category": "slow_speech",
        "reference": "Please switch the active voice profile to Windows SAPI David and confirm status",
        "rate": -3,  # Slow (-3)
        "voice_gender": "female",
        "noise_db": None,
        "pause_s": 0.0,
    },

    # Category 5: Technical Terminology & Programming
    {
        "id": "tech_01_fastapi",
        "category": "technical",
        "reference": "Write a FastAPI asynchronous route with Pydantic validation and error handling",
        "rate": 0,
        "voice_gender": "male",
        "noise_db": None,
        "pause_s": 0.0,
    },
    {
        "id": "tech_02_whisper",
        "category": "technical",
        "reference": "Configure faster-whisper with CTranslate2 int8 quantization and Silero VAD filtering",
        "rate": 0,
        "voice_gender": "female",
        "noise_db": None,
        "pause_s": 0.0,
    },

    # Category 6: Background Noise & Environmental Interference
    {
        "id": "noise_01_office",
        "category": "background_noise",
        "reference": "JARVIS open the terminal and execute python main.py",
        "rate": 0,
        "voice_gender": "male",
        "noise_db": 18,  # Additive room noise (SNR ~18 dB)
        "pause_s": 0.0,
    },

    # Category 7: Pauses & Silence Handling
    {
        "id": "pause_01_mid_sentence",
        "category": "pauses",
        "reference": "Check the weather forecast and then open my calendar for tomorrow",
        "rate": 0,
        "voice_gender": "female",
        "noise_db": None,
        "pause_s": 1.2,  # 1.2s silence inserted between clauses
    },

    # Category 8: Low Volume / Soft Utterance (Near threshold)
    {
        "id": "vol_01_soft",
        "category": "soft_speech",
        "reference": "Mute volume and turn off holographic interface",
        "rate": 0,
        "voice_gender": "male",
        "noise_db": None,
        "pause_s": 0.0,
        "attenuate": 0.35,  # Reduced amplitude
    }
]

def add_noise_and_modify(input_path, output_path, noise_db=None, pause_s=0.0, attenuate=1.0):
    with wave.open(input_path, "rb") as wf:
        n_channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        framerate = wf.getframerate()
        n_frames = wf.getnframes()
        raw_bytes = wf.readframes(n_frames)

    fmt = f"<{n_frames * n_channels}h"
    samples = list(struct.unpack(fmt, raw_bytes))

    if attenuate != 1.0:
        samples = [int(s * attenuate) for s in samples]

    if pause_s > 0:
        pause_frames = int(framerate * pause_s)
        mid_idx = len(samples) // 2
        samples = samples[:mid_idx] + [0] * (pause_frames * n_channels) + samples[mid_idx:]

    if noise_db is not None:
        rms = math.sqrt(sum(s**2 for s in samples) / max(len(samples), 1))
        noise_amp = rms / (10 ** (noise_db / 20.0)) if rms > 0 else 100
        noisy_samples = []
        for s in samples:
            noise = random.gauss(0, noise_amp)
            val = int(s + noise)
            val = max(-32768, min(32767, val))
            noisy_samples.append(val)
        samples = noisy_samples

    out_fmt = f"<{len(samples)}h"
    out_bytes = struct.pack(out_fmt, *samples)
    with wave.open(output_path, "wb") as wf:
        wf.setnchannels(n_channels)
        wf.setsampwidth(sampwidth)
        wf.setframerate(framerate)
        wf.writeframes(out_bytes)

def generate_benchmark_audio():
    print(f"Generating STT Benchmark Dataset in {DATASET_DIR}...")
    manifest = []

    sp_voice = win32com.client.Dispatch("SAPI.SpVoice")
    voices = sp_voice.GetVoices()
    david_idx = 0
    zira_idx = 0
    for idx in range(voices.Count):
        desc = voices.Item(idx).GetDescription().lower()
        if "david" in desc:
            david_idx = idx
        elif "zira" in desc:
            zira_idx = idx

    for tc in BENCHMARK_CASES:
        raw_wav = os.path.join(DATASET_DIR, f"{tc['id']}_raw.wav")
        final_wav = os.path.join(DATASET_DIR, f"{tc['id']}.wav")

        sp_voice.Rate = tc["rate"]
        target_voice_idx = zira_idx if tc["voice_gender"] == "female" else david_idx
        sp_voice.Voice = voices.Item(target_voice_idx)

        # Write to file stream (SSFMCreateForWrite = 3)
        sp_stream = win32com.client.Dispatch("SAPI.SpFileStream")
        sp_stream.Open(raw_wav, 3)
        sp_voice.AudioOutputStream = sp_stream
        sp_voice.Speak(tc["reference"])
        sp_stream.Close()

        # Modify with noise/pause/attenuation
        add_noise_and_modify(
            raw_wav,
            final_wav,
            noise_db=tc.get("noise_db"),
            pause_s=tc.get("pause_s", 0.0),
            attenuate=tc.get("attenuate", 1.0)
        )

        if os.path.exists(raw_wav):
            os.remove(raw_wav)

        with wave.open(final_wav, "rb") as wf:
            dur = wf.getnframes() / float(wf.getframerate())
            sr = wf.getframerate()

        manifest.append({
            "id": tc["id"],
            "category": tc["category"],
            "reference": tc["reference"],
            "file": final_wav,
            "filename": os.path.basename(final_wav),
            "duration_s": round(dur, 3),
            "sample_rate": sr,
            "rate": tc["rate"],
            "noise_db": tc.get("noise_db"),
            "pause_s": tc.get("pause_s", 0.0),
        })
        print(f"[{tc['category']}] Generated {tc['id']}: {dur:.2f}s - '{tc['reference'][:45]}...'")

    manifest_path = os.path.join(DATASET_DIR, "manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    print(f"\nSuccessfully generated {len(manifest)} test cases.")
    print(f"Manifest saved to: {manifest_path}")

if __name__ == "__main__":
    generate_benchmark_audio()
