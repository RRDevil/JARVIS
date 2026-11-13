import sys
import os
import json
import asyncio
sys.path.insert(0, 'backend')
sys.path.insert(0, '.')
from app.voice.stt.whisper import FasterWhisperSTTProvider
from engines.voice_eval.stt.benchmark_stt import compute_wer, compute_cer

provider = FasterWhisperSTTProvider(model_size='base.en')
with open('engines/voice_eval/stt/dataset/manifest.json', encoding='utf-8') as f:
    manifest = json.load(f)

async def test_prod():
    wers = []
    cers = []
    print("Testing Production FasterWhisperSTTProvider settings:")
    for item in manifest:
        with open(item['file'], 'rb') as f:
            audio_bytes = f.read()
        res = await provider.transcribe(audio_bytes, filename=item['filename'])
        wer = compute_wer(item['reference'], res.text)
        cer = compute_cer(item['reference'], res.text)
        wers.append(wer)
        cers.append(cer)
        print(f"[{item['id']}] REF: \"{item['reference']}\"")
        print(f"               HYP: \"{res.text}\" (WER: {wer*100:.1f}%, time: {res.duration_seconds}s)")
    avg_wer = sum(wers) / len(wers)
    avg_cer = sum(cers) / len(cers)
    print("=" * 65)
    print(f"Production Overall Average WER: {avg_wer*100:.2f}%")
    print(f"Production Overall Average CER: {avg_cer*100:.2f}%")
    print("=" * 65)

if __name__ == "__main__":
    asyncio.run(test_prod())
