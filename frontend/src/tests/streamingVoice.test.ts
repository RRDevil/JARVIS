import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { StreamingVoiceOrchestrator } from '../services/streamingVoice';
import { DEFAULT_VOICE_SETTINGS } from '../types/settings';
import * as api from '../services/api';

vi.mock('../services/api', () => ({
  synthesizeSpeech: vi.fn(),
}));

describe('Full-Response Neural Speech Orchestrator Pipeline', () => {
  let orchestrator: StreamingVoiceOrchestrator;

  beforeEach(() => {
    orchestrator = new StreamingVoiceOrchestrator();

    // Mock HTMLAudioElement
    vi.stubGlobal(
      'Audio',
      class MockAudio {
        src = '';
        volume = 1.0;
        currentTime = 0;
        onplay: (() => void) | null = null;
        onended: (() => void) | null = null;
        onerror: ((err: any) => void) | null = null;

        play() {
          if (this.onplay) {
            setTimeout(() => this.onplay?.(), 0);
          }
          return Promise.resolve();
        }
        pause() {}
        load() {}
      }
    );

    vi.mocked(api.synthesizeSpeech).mockResolvedValue({
      audio_base64: 'UklGRiQAAABXQVZFZm10IBAAAAABAAEARKwAAIhYAQACABAAZGF0YQAAAAA=',
      mime_type: 'audio/wav',
      duration_seconds: 3.5,
      voice_used: 'piper-lessac',
      provider_used: 'piper',
      fallback_applied: false,
    });
  });

  afterEach(() => {
    orchestrator.stop();
    vi.restoreAllMocks();
  });

  it('accumulates streamed tokens and synthesizes the full response in a single call', async () => {
    let playbackStarted = false;

    orchestrator.startSession(DEFAULT_VOICE_SETTINGS, {
      onPlaybackStart: () => {
        playbackStarted = true;
      },
    });

    // Simulate Gemini streaming tokens
    orchestrator.appendDelta('Good morning, sir. ');
    orchestrator.appendDelta('All core systems are nominal! ');
    orchestrator.appendDelta('Standing by for your command.');

    // During streaming, no synthesis should have occurred yet
    expect(api.synthesizeSpeech).not.toHaveBeenCalled();

    // Generation completes
    await orchestrator.flushAndComplete();

    // Verify exactly ONE single synthesis request with normalized text
    expect(api.synthesizeSpeech).toHaveBeenCalledTimes(1);
    const callArg = vi.mocked(api.synthesizeSpeech).mock.calls[0][0];
    expect(callArg.text).toContain('Good morning, sir.');
    expect(callArg.text).toContain('All core systems are nominal!');
    expect(callArg.delivery_profile).toBe('relaxed');
    expect(playbackStarted || orchestrator.isSpeaking()).toBeDefined();
  });

  it('immediately halts playback and aborts in-flight synthesis when stop() is called', async () => {
    let playbackStarted = false;

    // Simulate slow synthesis
    let resolveSynthesis: any;
    vi.mocked(api.synthesizeSpeech).mockReturnValue(
      new Promise((res) => {
        resolveSynthesis = res;
      })
    );

    orchestrator.startSession(DEFAULT_VOICE_SETTINGS, {
      onPlaybackStart: () => {
        playbackStarted = true;
      },
    });

    orchestrator.appendDelta('Cancelling this response midway.');
    const flushPromise = orchestrator.flushAndComplete();

    // User interrupts before synthesis resolves
    orchestrator.stop();
    expect(orchestrator.isSpeaking()).toBe(false);

    // Now synthesis resolves late
    resolveSynthesis({
      audio_base64: 'UklGRiQAAABXQVZFZm10IBAAAAABAAEARKwAAIhYAQACABAAZGF0YQAAAAA=',
      mime_type: 'audio/wav',
      duration_seconds: 2.0,
      voice_used: 'piper-lessac',
      provider_used: 'piper',
      fallback_applied: false,
    });
    await flushPromise;

    // Audio must not have played because session was cancelled
    expect(playbackStarted).toBe(false);
  });

  it('prevents leftover audio from playing when a new session supersedes an in-flight request', async () => {
    let session1Played = false;

    let resolveFirstSynth: any;
    vi.mocked(api.synthesizeSpeech).mockReturnValueOnce(
      new Promise((res) => {
        resolveFirstSynth = res;
      })
    );

    // Request 1 starts
    orchestrator.startSession(DEFAULT_VOICE_SETTINGS, {
      onPlaybackStart: () => {
        session1Played = true;
      },
    });
    orchestrator.appendDelta('First query response.');
    const req1Promise = orchestrator.flushAndComplete();

    // Request 2 arrives and immediately starts new session
    orchestrator.startSession(DEFAULT_VOICE_SETTINGS, {});
    orchestrator.appendDelta('Second query response.');

    // Now Request 1's backend call resolves late
    resolveFirstSynth({
      audio_base64: 'UklGRiQAAABXQVZFZm10IBAAAAABAAEARKwAAIhYAQACABAAZGF0YQAAAAA=',
      mime_type: 'audio/wav',
      duration_seconds: 2.0,
      voice_used: 'piper-lessac',
      provider_used: 'piper',
      fallback_applied: false,
    });
    await req1Promise;

    expect(session1Played).toBe(false); // Stale request discarded!
  });

  it('emits comprehensive latency and duration telemetry upon audio start', async () => {
    let capturedMetrics: any = null;

    orchestrator.startSession(DEFAULT_VOICE_SETTINGS, {
      onMetricsUpdate: (m) => {
        capturedMetrics = m;
      },
    });

    orchestrator.appendDelta('Diagnostic telemetry report.');
    await orchestrator.flushAndComplete();

    // Wait for mock audio onplay callback
    await new Promise((r) => setTimeout(r, 10));

    expect(capturedMetrics).toBeDefined();
    expect(capturedMetrics.totalDurationSeconds).toBe(3.5);
    expect(capturedMetrics.characterCount).toBeGreaterThan(0);
    expect(capturedMetrics.wordCount).toBe(3);
    expect(capturedMetrics.synthesisDurationMs).toBeGreaterThanOrEqual(0);
  });

  it('applies delivery profile prosody parameters to full response', async () => {
    const conversationalSettings = {
      ...DEFAULT_VOICE_SETTINGS,
      deliveryProfile: 'conversational' as const,
    };

    orchestrator.startSession(conversationalSettings);
    orchestrator.appendDelta('Testing conversational delivery parameters.');
    await orchestrator.flushAndComplete();

    expect(api.synthesizeSpeech).toHaveBeenCalledWith(
      expect.objectContaining({
        delivery_profile: 'conversational',
        noise_scale: 0.45,
        noise_w_scale: 0.6,
        length_scale: 1.0,
      })
    );
  });

  it('handles empty and whitespace responses without crashing or hanging', async () => {
    let completed = false;

    orchestrator.startSession(DEFAULT_VOICE_SETTINGS, {
      onPlaybackComplete: () => {
        completed = true;
      },
    });

    orchestrator.appendDelta('    \n\n   ');
    await orchestrator.flushAndComplete();

    expect(api.synthesizeSpeech).not.toHaveBeenCalled();
    expect(completed).toBe(true);
    expect(orchestrator.isSpeaking()).toBe(false);
  });

  it('handles backend synthesis failure safely without leaving orchestrator stuck', async () => {
    let errorCaught: any = null;
    vi.mocked(api.synthesizeSpeech).mockRejectedValueOnce(new Error('Persistent worker crash'));

    orchestrator.startSession(DEFAULT_VOICE_SETTINGS, {
      onError: (err) => {
        errorCaught = err;
      },
    });

    orchestrator.appendDelta('This request will fail on the backend.');
    await orchestrator.flushAndComplete();

    expect(errorCaught).toBeDefined();
    expect(errorCaught.message).toBe('Persistent worker crash');
    expect(orchestrator.isSpeaking()).toBe(false);
  });
});
