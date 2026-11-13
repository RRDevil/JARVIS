/**
 * Full-Response Neural Speech Orchestrator for J.A.R.V.I.S.
 *
 * Replaces sentence-level chunking with coherent full-response synthesis.
 * Accumulates streaming Gemini response tokens in real-time, normalizes the complete
 * text on generation completion, and executes a single unified synthesis request
 * against the persistent Piper worker (or active TTS engine).
 * Delivers natural, continuous, and prosodically smooth speech without artificial pauses.
 */

import { VoiceSettings } from '../types/settings';
import { synthesizeSpeech } from './api';
import { normalizeTextForSpeech } from './textNormalizer';
import { speechTiming } from './speechTiming';
import { NarrationPriority } from '../types/narration';
import { speechQueue } from './speechQueue';

export interface StreamingVoiceCallbacks {
  onStart?: () => void;
  onPlaybackStart?: () => void;
  onSegmentStart?: (index: number, text: string) => void;
  onPlaybackComplete?: () => void;
  onError?: (err: any) => void;
  onMetricsUpdate?: (metrics: StreamingMetrics) => void;
}

export interface StreamingMetrics {
  timeToFirstTokenMs?: number;       // From session start to first Gemini SSE token
  geminiCompletionTimeMs?: number;   // From session start to Gemini stream completion
  synthesisDurationMs?: number;      // Duration of full-response synthesis request
  completionToPlaybackMs?: number;   // From Gemini completion to first audio playback
  totalTimeToPlaybackMs?: number;    // Total latency: from session start to first audio playback
  totalDurationSeconds?: number;     // Total audio duration in seconds
  realTimeFactor?: number;           // synthesisDurationSec / totalDurationSeconds
  characterCount?: number;           // Normalized speech text character length
  wordCount?: number;                // Word count of speech text
  activeProfileId?: string;          // Voice profile used
  providerUsed?: string;             // TTS engine provider used
}

export class StreamingVoiceOrchestrator {
  private settings: VoiceSettings | null = null;
  private callbacks: StreamingVoiceCallbacks = {};
  private activeSequenceId = 0;
  private isSessionActive = false;
  private isSynthesizing = false;
  private isPlaying = false;

  private accumulatedText = '';
  private currentAudio: HTMLAudioElement | null = null;

  // Telemetry timestamps
  private startTime = 0;
  private firstTokenTime = 0;
  private geminiCompletionTime = 0;
  private synthesisStartTime = 0;
  private synthesisEndTime = 0;
  private firstAudioTime = 0;
  private totalAudioDurationSec = 0;
  private characterCount = 0;
  private wordCount = 0;
  private providerUsed = '';

  private taskId = 'turn-response';

  /**
   * Initializes a new full-response speech synthesis session.
   * Invalidates any previous pending synthesis or active playback.
   */
  public startSession(settings: VoiceSettings, callbacks: StreamingVoiceCallbacks = {}, taskId: string = 'turn-response'): void {
    this.stop();

    this.settings = settings;
    this.callbacks = callbacks;
    this.taskId = taskId || 'turn-response';
    speechQueue.clearCancelledTask(this.taskId);
    this.isSessionActive = true;
    this.isSynthesizing = false;
    this.isPlaying = false;
    this.accumulatedText = '';

    this.startTime = performance.now();
    this.firstTokenTime = 0;
    this.geminiCompletionTime = 0;
    this.synthesisStartTime = 0;
    this.synthesisEndTime = 0;
    this.firstAudioTime = 0;
    this.totalAudioDurationSec = 0;
    this.characterCount = 0;
    this.wordCount = 0;
    this.providerUsed = '';

    this.callbacks.onStart?.();
  }

  /**
   * Accumulates an incoming token chunk from the Gemini SSE stream.
   * Does NOT slice or synthesize sentences mid-stream, preserving smooth full-response flow.
   */
  public appendDelta(delta: string): void {
    if (!this.isSessionActive) return;

    if (this.firstTokenTime === 0 && delta) {
      this.firstTokenTime = performance.now();
    }

    this.accumulatedText += delta;
  }

  /**
   * Called when Gemini generation completes.
   * Normalizes the full accumulated text and submits a single unified synthesis request.
   */
  public async flushAndComplete(fullTextOverride?: string): Promise<void> {
    if (!this.isSessionActive || !this.settings) return;

    this.geminiCompletionTime = performance.now();
    const rawText = (typeof fullTextOverride === 'string' && fullTextOverride.length > 0)
      ? fullTextOverride
      : this.accumulatedText;

    if (!rawText || !rawText.trim()) {
      this.isSessionActive = false;
      this.callbacks.onPlaybackComplete?.();
      return;
    }

    // 1. Comprehensive speech text normalization
    const speechText = normalizeTextForSpeech(rawText);
    if (!speechText || !speechText.trim()) {
      this.isSessionActive = false;
      this.callbacks.onPlaybackComplete?.();
      return;
    }

    this.characterCount = speechText.length;
    this.wordCount = speechText.trim().split(/\s+/).length;

    // 2. Prepare acoustic prosody configuration from delivery profile
    const profile = this.settings.deliveryProfile || 'relaxed';
    const profileConfig = speechTiming.getProfileConfig(profile);
    const seqId = this.activeSequenceId;

    this.isSynthesizing = true;
    this.synthesisStartTime = performance.now();

    try {
      // 3. Single unified synthesis call for the complete response
      const resp = await synthesizeSpeech({
        text: speechText,
        profile_id: this.settings.activeProfileId || undefined,
        voice_id: this.settings.selectedVoiceId || undefined,
        rate: this.settings.speakingRate,
        volume: this.settings.volume,
        pitch: this.settings.pitch,
        delivery_profile: profile,
        noise_scale: profileConfig.noiseScale,
        noise_w_scale: profileConfig.noiseWScale,
        length_scale: profileConfig.lengthScale,
        metadata: {
          emotional_intensity: this.settings.emotionalIntensity ?? 1.0,
          personality: this.settings.speechPersonality || 'balanced_cinematic',
          context: 'conversation',
        },
      });

      // Cancellation check: verify session has not been superseded or stopped during synthesis
      if (!this.isSessionActive || seqId !== this.activeSequenceId) {
        return;
      }

      this.synthesisEndTime = performance.now();
      this.isSynthesizing = false;
      this.totalAudioDurationSec = resp.duration_seconds || 0;
      this.providerUsed = resp.provider_used || '';

      if (!resp.audio_base64) {
        this.isSessionActive = false;
        this.callbacks.onPlaybackComplete?.();
        return;
      }

      // 4. Delegate to authoritative centralized SpeechQueue to strictly enforce single-voice playback
      await speechQueue.enqueuePreSynthesized(
        resp.audio_base64,
        speechText,
        NarrationPriority.FINAL_RESPONSE,
        this.taskId || 'turn-response',
        this.settings,
        {
          onStart: () => {
            if (this.isSessionActive && seqId === this.activeSequenceId) {
              this.isPlaying = true;
              this.firstAudioTime = performance.now();
              this.callbacks.onPlaybackStart?.();
              this.callbacks.onSegmentStart?.(0, speechText);
              this.emitMetrics();
            }
          },
          onComplete: () => {
            this.isPlaying = false;
            this.isSessionActive = false;
            this.callbacks.onPlaybackComplete?.();
            this.emitMetrics();
          },
          onError: (err) => {
            this.isPlaying = false;
            this.isSessionActive = false;
            this.callbacks.onError?.(err);
          },
        }
      );
    } catch (err: any) {
      this.isSynthesizing = false;
      if (this.isSessionActive && seqId === this.activeSequenceId) {
        this.isSessionActive = false;
        console.warn('[StreamingVoice] Full-response synthesis fault:', err);
        this.callbacks.onError?.(err);
      }
    }
  }

  /**
   * Calculates and emits updated latency, duration, and RTF telemetry metrics.
   */
  private emitMetrics(): void {
    const synDurMs = this.synthesisEndTime > 0 && this.synthesisStartTime > 0
      ? Math.round(this.synthesisEndTime - this.synthesisStartTime)
      : undefined;

    const rtf = this.totalAudioDurationSec > 0 && synDurMs !== undefined
      ? Number(((synDurMs / 1000) / this.totalAudioDurationSec).toFixed(3))
      : undefined;

    const metrics: StreamingMetrics = {
      timeToFirstTokenMs: this.firstTokenTime > 0 ? Math.round(this.firstTokenTime - this.startTime) : undefined,
      geminiCompletionTimeMs: this.geminiCompletionTime > 0 ? Math.round(this.geminiCompletionTime - this.startTime) : undefined,
      synthesisDurationMs: synDurMs,
      completionToPlaybackMs: this.firstAudioTime > 0 && this.geminiCompletionTime > 0
        ? Math.round(this.firstAudioTime - this.geminiCompletionTime)
        : undefined,
      totalTimeToPlaybackMs: this.firstAudioTime > 0 ? Math.round(this.firstAudioTime - this.startTime) : undefined,
      totalDurationSeconds: Number(this.totalAudioDurationSec.toFixed(2)),
      realTimeFactor: rtf,
      characterCount: this.characterCount,
      wordCount: this.wordCount,
      activeProfileId: this.settings?.activeProfileId,
      providerUsed: this.providerUsed,
    };

    this.callbacks.onMetricsUpdate?.(metrics);
  }

  /**
   * Halts active speech synthesis and playback immediately.
   * Cancels in-flight synthesis jobs and frees audio resources.
   */
  public stop(): void {
    this.isSessionActive = false;
    this.isSynthesizing = false;
    this.isPlaying = false;
    this.activeSequenceId++;
    this.accumulatedText = '';

    if (this.taskId) {
      speechQueue.cancelTask(this.taskId);
    }

    if (this.currentAudio) {
      try {
        this.currentAudio.pause();
        this.currentAudio.currentTime = 0;
        this.currentAudio.src = '';
      } catch {
        // Safe disposal
      }
      this.currentAudio = null;
    }
  }

  /**
   * Checks whether the orchestrator is currently synthesizing or actively speaking.
   */
  public isSpeaking(): boolean {
    return this.isPlaying || this.isSynthesizing;
  }
}

// Global Singleton Instance
export const streamingVoice = new StreamingVoiceOrchestrator();
