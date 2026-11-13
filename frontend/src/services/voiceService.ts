import { VoiceSettings } from '../types/settings';
import { synthesizeSpeech } from './api';
import { normalizeTextForSpeech } from './textNormalizer';

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
  private currentAudio: HTMLAudioElement | null = null;
  private currentOnEnded: (() => void) | null = null;
  private isCurrentlyPlaying = false;
  private currentPlayId = 0;

  public isPlaying(): boolean {
    return this.isCurrentlyPlaying;
  }

  public async playBase64Wav(
    base64Wav: string,
    options: {
      volume?: number;
      onStart?: () => void;
      onEnded?: () => void;
      onError?: (err: any) => void;
    } = {}
  ): Promise<void> {
    // Interrupt and halt any existing audio stream immediately
    this.stop();

    if (!base64Wav) {
      options.onEnded?.();
      return;
    }

    const audioUrl = `data:audio/wav;base64,${base64Wav}`;
    const audio = new Audio(audioUrl);
    this.currentAudio = audio;
    this.currentOnEnded = options.onEnded || null;
    this.isCurrentlyPlaying = true;

    // Apply volume (0.0 to 1.0)
    const volumeLevel = typeof options.volume === 'number' ? Math.max(0, Math.min(100, options.volume)) / 100 : 1.0;
    audio.volume = volumeLevel;

    let startTriggered = false;
    const triggerStart = () => {
      if (!startTriggered) {
        startTriggered = true;
        this.isCurrentlyPlaying = true;
        options.onStart?.();
      }
    };

    audio.onplay = () => {
      triggerStart();
    };

    audio.onended = () => {
      this.isCurrentlyPlaying = false;
      this.currentAudio = null;
      const callback = this.currentOnEnded;
      this.currentOnEnded = null;
      callback?.();
    };

    audio.onerror = (e) => {
      this.isCurrentlyPlaying = false;
      this.currentAudio = null;
      this.currentOnEnded = null;
      options.onError?.(e);
    };

    try {
      await audio.play();
      triggerStart();
    } catch (err) {
      this.isCurrentlyPlaying = false;
      this.currentAudio = null;
      this.currentOnEnded = null;
      options.onError?.(err);
    }
  }

  /**
   * Immediately halts current speech playback.
   */
  public stop(): void {
    this.currentPlayId++;
    if (this.currentAudio) {
      try {
        this.currentAudio.pause();
        this.currentAudio.currentTime = 0;
        this.currentAudio.src = '';
      } catch {
        // ignore
      }
      this.currentAudio = null;
    }

    if (this.isCurrentlyPlaying) {
      this.isCurrentlyPlaying = false;
      const callback = this.currentOnEnded;
      this.currentOnEnded = null;
      callback?.();
    }
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

