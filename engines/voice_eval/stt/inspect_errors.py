import json

with open('engines/voice_eval/stt/results/stt_benchmark_results.json', encoding='utf-8') as f:
    data = json.load(f)

for cfg in data:
    print('=' * 70)
    print(cfg['config'])
    errors = [d for d in cfg['details'] if d['wer'] > 0]
    print(f"Total error cases: {len(errors)}/{len(cfg['details'])}")
    for e in errors:
        print(f" - [{e['id']}]")
        print(f"   REF: \"{e['reference']}\"")
        print(f"   HYP: \"{e['hypothesis']}\"")
        print(f"   WER: {e['wer']*100:.1f}%, Latency: {e['latency_ms']}ms")

