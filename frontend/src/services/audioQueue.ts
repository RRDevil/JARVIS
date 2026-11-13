import { BoundaryType, DeliveryProfile, speechTiming } from './speechTiming';

export interface AudioSegment {
  index: number;
  text: string;
  audioBase64: string;
  durationSeconds: number;
  isLast: boolean;
  boundaryType?: BoundaryType;
  deliveryProfile?: DeliveryProfile;
}

export interface AudioQueueCallbacks {
  onPlaybackStart?: (segment: AudioSegment) => void;
  onSegmentStart?: (segment: AudioSegment) => void;
  onSegmentEnd?: (segment: AudioSegment, gapMs: number) => void;
  onPlaybackComplete?: () => void;
  onError?: (err: any) => void;
}

export interface PlaybackMetrics {
  totalSegments: number;
  totalDurationSeconds: number;
  playbackGapsMs: number[];
  timeToFirstAudioMs?: number;
}

/**
 * High-Performance Gapless Audio Segment Queue.
 *
 * Ensures sequential in-order playback of chunked TTS audio segments,
 * pre-buffers subsequent segments to eliminate inter-segment silence (<15ms),
 * and handles instantaneous cancellation and interruption.
 */
export class AudioSegmentQueue {
  private pendingSegments = new Map<number, AudioSegment>();
  private nextPlayIndex = 0;
  private isPlaying = false;
  private isLastReceived = false;
  private lastIndex: number | null = null;
  private currentSequenceId = 0;
  private volume = 1.0;

  private currentAudio: HTMLAudioElement | null = null;
  private preloadedAudio: HTMLAudioElement | null = null;
  private preloadedIndex: number | null = null;
  private pauseTimer: any = null;

  private lastSegmentEndTime = 0;
  private queueStartTime = 0;
  private playbackStarted = false;

  private callbacks: AudioQueueCallbacks = {};
  private metrics: PlaybackMetrics = {
    totalSegments: 0,
    totalDurationSeconds: 0,
    playbackGapsMs: [],
  };

  constructor(callbacks: AudioQueueCallbacks = {}) {
    this.callbacks = callbacks;
  }

  public setCallbacks(callbacks: AudioQueueCallbacks): void {
    this.callbacks = callbacks;
  }

  public setVolume(volume0to100: number): void {
    this.volume = Math.max(0, Math.min(100, volume0to100)) / 100;
    if (this.currentAudio) {
      this.currentAudio.volume = this.volume;
    }
    if (this.preloadedAudio) {
      this.preloadedAudio.volume = this.volume;
    }
  }

  /**
   * Reset queue for a new speech streaming session.
   * Returns a fresh sequence token.
   */
  public startSession(volume0to100 = 100): number {
    this.stop();
    if (this.pauseTimer) {
      clearTimeout(this.pauseTimer);
      this.pauseTimer = null;
    }
    this.currentSequenceId++;
    this.pendingSegments.clear();
    this.nextPlayIndex = 0;
    this.isPlaying = false;
    this.isLastReceived = false;
    this.lastIndex = null;
    this.playbackStarted = false;
    this.lastSegmentEndTime = 0;
    this.queueStartTime = performance.now();
    this.setVolume(volume0to100);

    this.metrics = {
      totalSegments: 0,
      totalDurationSeconds: 0,
      playbackGapsMs: [],
    };

    return this.currentSequenceId;
  }

  /**
   * Enqueue a newly synthesized audio segment.
   */
  public enqueue(segment: AudioSegment, sequenceId: number): void {
    if (sequenceId !== this.currentSequenceId) {
      // Discard segment from stale or cancelled session
      return;
    }

    if (segment.isLast) {
      this.isLastReceived = true;
      this.lastIndex = segment.index;
    }

    if (segment.audioBase64) {
      this.pendingSegments.set(segment.index, segment);
      this.metrics.totalSegments++;
      this.metrics.totalDurationSeconds += segment.durationSeconds;
    } else {
      // Store blank segment placeholder so the queue index can advance
      this.pendingSegments.set(segment.index, {
        ...segment,
        audioBase64: '',
        durationSeconds: 0,
      });
    }

    // Check if we can begin playback or preload
    if (!this.isPlaying && this.pauseTimer === null) {
      this.tryPlayNext();
    } else {
      this.tryPreloadNext();
    }
  }

  /**
   * Signal that no more text will be streamed from LLM.
   */
  public markStreamComplete(lastIndex: number, sequenceId: number): void {
    if (sequenceId !== this.currentSequenceId) return;

    this.isLastReceived = true;
    this.lastIndex = lastIndex;

    // Only finish playback if there were no speech segments at all (lastIndex < 0),
    // or if the final segment has ALREADY finished playing (nextPlayIndex > lastIndex).
    // NEVER finish playback prematurely just because pendingSegments is temporarily empty
    // while synthesis jobs are still in flight!
    if (!this.isPlaying && this.pauseTimer === null) {
      if (lastIndex < 0 || this.nextPlayIndex > lastIndex) {
        this.finishPlayback();
      }
    }
  }

  private tryPlayNext(): void {
    if (this.isPlaying) return;

    const segment = this.pendingSegments.get(this.nextPlayIndex);
    if (!segment) {
      if (this.isLastReceived && (this.lastIndex === null || this.nextPlayIndex > this.lastIndex)) {
        this.finishPlayback();
      }
      return;
    }

    this.pendingSegments.delete(this.nextPlayIndex);

    // If segment has no audio bytes, advance immediately to next index
    if (!segment.audioBase64) {
      this.nextPlayIndex++;
      this.tryPlayNext();
      return;
    }

    this.playSegment(segment);
  }

  private playSegment(segment: AudioSegment): void {
    this.isPlaying = true;

    // Calculate gap since last segment
    let gapMs = 0;
    if (this.lastSegmentEndTime > 0) {
      gapMs = Math.round(performance.now() - this.lastSegmentEndTime);
      this.metrics.playbackGapsMs.push(gapMs);
    }

    if (!this.playbackStarted) {
      this.playbackStarted = true;
      this.metrics.timeToFirstAudioMs = Math.round(performance.now() - this.queueStartTime);
      this.callbacks.onPlaybackStart?.(segment);
    }

    this.callbacks.onSegmentStart?.(segment);

    let audio: HTMLAudioElement;

    // Check if segment was already preloaded
    if (this.preloadedAudio && this.preloadedIndex === segment.index) {
      audio = this.preloadedAudio;
      this.preloadedAudio = null;
      this.preloadedIndex = null;
    } else {
      const audioUrl = `data:audio/wav;base64,${segment.audioBase64}`;
      audio = new Audio(audioUrl);
      audio.volume = this.volume;
    }

    this.currentAudio = audio;

    // Immediately attempt to preload the subsequent segment (nextPlayIndex + 1)
    const subsequentIndex = segment.index + 1;
    this.preloadSegment(subsequentIndex);

    const onAudioEnded = () => {
      this.lastSegmentEndTime = performance.now();
      this.callbacks.onSegmentEnd?.(segment, gapMs);

      this.currentAudio = null;
      this.isPlaying = false;
      this.nextPlayIndex = segment.index + 1;

      // Check if we are done with all segments
      const isCompletelyDone = this.isLastReceived && (this.lastIndex === null || segment.index >= this.lastIndex);
      if (isCompletelyDone) {
        this.finishPlayback();
        return;
      }

      // Calculate prosodic pause before next segment based on structural boundary and delivery profile
      const pauseMs = speechTiming.calculatePauseDurationMs(segment.boundaryType || 'sentence', segment.deliveryProfile);
      if (pauseMs > 0) {
        this.pauseTimer = setTimeout(() => {
          this.pauseTimer = null;
          this.tryPlayNext();
        }, pauseMs);
      } else {
        this.tryPlayNext();
      }
    };

    audio.onended = onAudioEnded;

    audio.onerror = (err) => {
      console.warn(`[AudioQueue] Error playing segment #${segment.index}:`, err);
      this.callbacks.onError?.(err);
      onAudioEnded();
    };

    audio.play().catch((err) => {
      console.warn(`[AudioQueue] play() rejected for segment #${segment.index}:`, err);
      onAudioEnded();
    });
  }

  private preloadSegment(index: number): void {
    if (this.preloadedIndex === index && this.preloadedAudio) {
      return;
    }

    const nextSeg = this.pendingSegments.get(index);
    if (!nextSeg || !nextSeg.audioBase64) {
      return;
    }

    try {
      const url = `data:audio/wav;base64,${nextSeg.audioBase64}`;
      const preload = new Audio(url);
      preload.volume = this.volume;
      preload.preload = 'auto';
      preload.load();

      this.preloadedAudio = preload;
      this.preloadedIndex = index;
    } catch {
      // Ignore preload failure; standard playback will handle it
    }
  }

  private tryPreloadNext(): void {
    if (!this.preloadedAudio) {
      this.preloadSegment(this.nextPlayIndex + 1);
    }
  }

  private finishPlayback(): void {
    this.isPlaying = false;
    this.currentAudio = null;
    this.preloadedAudio = null;
    this.preloadedIndex = null;
    this.callbacks.onPlaybackComplete?.();
  }

  /**
   * Halts any playing audio immediately and flushes the queue.
   */
  public stop(): void {
    this.currentSequenceId++;
    this.pendingSegments.clear();
    this.isPlaying = false;
    this.playbackStarted = false;

    if (this.pauseTimer) {
      clearTimeout(this.pauseTimer);
      this.pauseTimer = null;
    }

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

    if (this.preloadedAudio) {
      try {
        this.preloadedAudio.pause();
        this.preloadedAudio.src = '';
      } catch {
        // ignore
      }
      this.preloadedAudio = null;
      this.preloadedIndex = null;
    }
  }

  public isAudioPlaying(): boolean {
    return this.isPlaying || this.pauseTimer !== null;
  }

  public getMetrics(): PlaybackMetrics {
    return { ...this.metrics };
  }
}

// Global Singleton
export const audioSegmentQueue = new AudioSegmentQueue();

