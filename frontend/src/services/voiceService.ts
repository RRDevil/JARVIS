import { VoiceSettings } from '../types/settings';
import { synthesizeSpeech } from './api';
import { normalizeTextForSpeech } from './textNormalizer';
import { speechQueue } from './speechQueue';
import { NarrationPriority } from '../types/narration';

/**
 * Strips code blocks, markdown formatting, technical markdown tokens,
 * URLs, and emojis, and normalizes numbers/acronyms to produce natural-sounding speech text.
 */
export function cleanTextForSpeech(text: string): string {
  return normalizeTextForSpeech(text);
}

/**
 * Microphone Audio Recording Service for Push-to-Talk.
 * Releases all audio tracks immediately upon stop/cancel to prevent
 * background microphone capture.
 */
export class AudioRecorder {
  private mediaRecorder: MediaRecorder | null = null;
  private stream: MediaStream | null = null;
  private audioChunks: Blob[] = [];
  private recordingState: 'inactive' | 'recording' | 'paused' = 'inactive';

  public isRecording(): boolean {
    return this.recordingState === 'recording';
  }

  public async start(): Promise<void> {
    if (this.recordingState === 'recording') {
      return;
    }

    if (typeof navigator === 'undefined' || !navigator.mediaDevices?.getUserMedia) {
      throw new Error('Microphone audio capture is not supported in this environment.');
    }

    this.audioChunks = [];

    try {
      this.stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          sampleRate: { ideal: 16000 },
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });
    } catch (err: any) {
      if (err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError') {
        throw new Error('Microphone permission was denied. Please allow microphone access.');
      } else if (err.name === 'NotFoundError' || err.name === 'DevicesNotFoundError') {
        throw new Error('No physical or virtual microphone was detected on this system.');
      }
      throw new Error(`Microphone access failed: ${err.message || err.name}`);
    }

    // Determine supported mime type
    let mimeType = 'audio/webm';
    if (typeof MediaRecorder.isTypeSupported === 'function') {
      if (MediaRecorder.isTypeSupported('audio/webm;codecs=opus')) {
        mimeType = 'audio/webm;codecs=opus';
      } else if (MediaRecorder.isTypeSupported('audio/ogg;codecs=opus')) {
        mimeType = 'audio/ogg;codecs=opus';
      } else if (MediaRecorder.isTypeSupported('audio/wav')) {
        mimeType = 'audio/wav';
      }
    }

    try {
      this.mediaRecorder = new MediaRecorder(this.stream, { mimeType });
    } catch {
      // Fallback without explicit mimeType
      this.mediaRecorder = new MediaRecorder(this.stream);
    }

    this.mediaRecorder.ondataavailable = (event: BlobEvent) => {
      if (event.data && event.data.size > 0) {
        this.audioChunks.push(event.data);
      }
    };

    this.mediaRecorder.start(100); // 100ms slice
    this.recordingState = 'recording';
  }

  public stop(): Promise<Blob> {
    return new Promise((resolve, reject) => {
      if (!this.mediaRecorder || this.recordingState !== 'recording') {
        this.cleanup();
        reject(new Error('No active recording in progress.'));
        return;
      }

      this.mediaRecorder.onstop = () => {
        const mime = this.mediaRecorder?.mimeType || 'audio/webm';
        const blob = new Blob(this.audioChunks, { type: mime });
        this.cleanup();
        resolve(blob);
      };

      try {
        if (this.mediaRecorder.state !== 'inactive') {
          try {
            this.mediaRecorder.requestData();
          } catch {
            // ignore
          }
          this.mediaRecorder.stop();
        } else {
          const mime = this.mediaRecorder?.mimeType || 'audio/webm';
          const blob = new Blob(this.audioChunks, { type: mime });
          this.cleanup();
          resolve(blob);
        }
        this.recordingState = 'inactive';
      } catch (err) {
        this.cleanup();
        reject(err);
      }
    });
  }

  public cancel(): void {
    if (this.mediaRecorder && this.recordingState === 'recording') {
      try {
        this.mediaRecorder.onstop = null;
        this.mediaRecorder.stop();
      } catch {
        // ignore
      }
    }
    this.cleanup();
  }

  private cleanup(): void {
    this.recordingState = 'inactive';
    this.mediaRecorder = null;
    this.audioChunks = [];

    // Explicitly stop all microphone stream tracks so hardware mic is released immediately
    if (this.stream) {
      this.stream.getTracks().forEach((track) => track.stop());
      this.stream = null;
    }
  }
}

/**
 * Text-to-Speech Playback Engine.
 * Enforces single-stream audio playback with instant interruption.
 */
export class VoicePlayer {
  private isCurrentlyPlaying = false;
  private currentPlayId = 0;

  public isPlaying(): boolean {
    return this.isCurrentlyPlaying || speechQueue.isSpeaking();
  }

  public async playBase64Wav(
    base64Wav: string,
    options: {
      volume?: number;
      priority?: NarrationPriority;
      taskId?: string;
      onStart?: () => void;
      onEnded?: () => void;
      onError?: (err: any) => void;
    } = {}
  ): Promise<void> {
    if (!base64Wav) {
      options.onEnded?.();
      return;
    }

    const priority = options.priority ?? NarrationPriority.PREVIEW;
    const taskId = options.taskId || 'preview-session';

    this.isCurrentlyPlaying = true;
    await speechQueue.enqueuePreSynthesized(
      base64Wav,
      priority === NarrationPriority.PREVIEW ? 'Voice Preview' : 'Spoken Audio',
      priority,
      taskId,
      { volume: options.volume ?? 100 } as any,
      {
        onStart: () => {
          this.isCurrentlyPlaying = true;
          options.onStart?.();
        },
        onComplete: () => {
          this.isCurrentlyPlaying = false;
          options.onEnded?.();
        },
        onError: (err) => {
          this.isCurrentlyPlaying = false;
          options.onError?.(err);
        },
      }
    );
  }

  /**
   * Immediately halts current speech playback.
   */
  public stop(): void {
    speechQueue.cancelTask('preview-session');
    speechQueue.cancelTask('conversational-response');
    this.isCurrentlyPlaying = false;
  }

  /**
   * Synthesize text and play spoken audio.
   */
  public async speakText(
    text: string,
    settings: VoiceSettings,
    callbacks: {
      onStart?: () => void;
      onEnded?: () => void;
      onError?: (err: any) => void;
    } = {}
  ): Promise<void> {
    const playId = ++this.currentPlayId;
    const speechText = cleanTextForSpeech(text);
    if (!speechText) {
      callbacks.onEnded?.();
      return;
    }

    try {
      const response = await synthesizeSpeech({
        text: speechText,
        profile_id: settings.activeProfileId || undefined,
        voice_id: settings.selectedVoiceId || undefined,
        rate: settings.speakingRate,
        volume: settings.volume,
        pitch: settings.pitch,
      });

      if (this.currentPlayId !== playId) {
        // Synthesis completed after user stopped or triggered new audio
        return;
      }

      if (!response.audio_base64) {
        callbacks.onEnded?.();
        return;
      }

      await this.playBase64Wav(response.audio_base64, {
        volume: settings.volume,
        priority: NarrationPriority.FINAL_RESPONSE,
        taskId: 'conversational-response',
        onStart: callbacks.onStart,
        onEnded: callbacks.onEnded,
        onError: callbacks.onError,
      });
    } catch (err) {
      if (this.currentPlayId === playId) {
        callbacks.onError?.(err);
      }
    }
  }
}

// Global Singleton instances
export const audioRecorder = new AudioRecorder();
export const voicePlayer = new VoicePlayer();

