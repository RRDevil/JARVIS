import sys
import os
sys.path.insert(0, 'backend')
from faster_whisper import WhisperModel

prompt_enriched = (
    "I am J.A.R.V.I.S., your desktop AI assistant. Sir, please open Notepad, "
    "Calculator, Google Chrome, File Explorer, terminal, PowerShell, Python, "
    "or take a screenshot. Configure settings, Windows SAPI 5, FastAPI, "
    "Pydantic, asynchronous routines, git status, and system diagnostics."
)

model = WhisperModel('base.en', device='cpu', compute_type='int8', download_root='data/models/stt')

test_files = [
    ('speed_02_slow', 'engines/voice_eval/stt/dataset/speed_02_slow.wav'),
    ('tech_01_fastapi', 'engines/voice_eval/stt/dataset/tech_01_fastapi.wav'),
    ('tech_02_whisper', 'engines/voice_eval/stt/dataset/tech_02_whisper.wav'),
]

print("TESTING ENRICHED CONTEXTUAL PROMPT WITH base.en:")
for name, fpath in test_files:
    segs, _ = model.transcribe(
        fpath,
        beam_size=1,
        language='en',
        initial_prompt=prompt_enriched,
        condition_on_previous_text=False
    )
    text = ' '.join(s.text.strip() for s in segs)
    print(f" - [{name}] -> \"{text}\"")

