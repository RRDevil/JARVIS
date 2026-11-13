/**
 * Centralized Authoritative Speech Playback Manager for J.A.R.V.I.S.
 *
 * Enforces strict architectural invariants:
 *   1. Exactly ONE active playback audio stream at a time across the entire application.
 *   2. Controlled priority queue:
 *        1. CRITICAL: Safety warnings, major exceptions.
 *        2. APPROVAL: Consequential approval requests and user confirmation decisions.
 *        3. ACKNOWLEDGMENT: Immediate task receipt acknowledgments.
 *        4. PROGRESS: Grounded execution progress updates (stale updates pruned).
 *        5. FINAL_RESPONSE: Full conversational summaries.
 *   3. Stable event IDs and deduplication (at most one spoken announcement per event/approval).
 *   4. Immediate interruption of obsolete speech (e.g. user approval instantly interrupts the request announcement).
 *   5. Automatic task and approval cancellation clearance.
 *   6. Monotonic sequence tracking preventing stale playback callbacks from resetting newer utterances.
 */

import { NarrationPriority } from '../types/narration';
import { VoiceSettings } from '../types/settings';
import { synthesizeSpeech } from './api';
import { normalizeTextForSpeech } from './textNormalizer';

export interface SpeechQueueItem {
  id: string;
  eventId?: string;
  text: string;
  priority: NarrationPriority;
  taskId: string;
  approvalId?: string;
  timestamp: number;
  metadata?: Record<string, any>;
  audioBase64?: string;
  onStart?: () => void;
  onComplete?: () => void;
  onError?: (err: any) => void;
}

export interface SpeechQueueCallbacks {
  onPlaybackStart?: (item: SpeechQueueItem) => void;
  onPlaybackComplete?: (item: SpeechQueueItem) => void;
  onQueueDrained?: () => void;
  onError?: (err: any, item: SpeechQueueItem) => void;
  onPreempt?: (cancelledItem: SpeechQueueItem, preemptingItem: SpeechQueueItem) => void;
}

export class PrioritizedSpeechQueue {
  private queue: SpeechQueueItem[] = [];
  private currentItem: SpeechQueueItem | null = null;
  private currentAudio: HTMLAudioElement | null = null;
  private isProcessing = false;
  private callbacks: SpeechQueueCallbacks = {};
  private activeSequenceId = 0;
  private announcedEventKeys = new Set<string>();

  constructor(callbacks: SpeechQueueCallbacks = {}) {
    this.callbacks = callbacks;
  }

  public setCallbacks(callbacks: SpeechQueueCallbacks): void {
    this.callbacks = callbacks;
  }

  public isSpeaking(): boolean {
    return this.currentItem !== null || this.isProcessing;
  }

  public getCurrentItem(): SpeechQueueItem | null {
    return this.currentItem;
  }

  public clearDeduplicationRegistry(): void {
    this.announcedEventKeys.clear();
  }

  /**
   * Enqueue a new spoken utterance into the prioritized speech queue.
   */
  public async enqueue(
    text: string,
    priority: NarrationPriority,
    taskId: string,
    voiceSettings: VoiceSettings,
    metadata?: Record<string, any>,
    options?: {
      eventId?: string;
      approvalId?: string;
      audioBase64?: string;
      onStart?: () => void;
      onComplete?: () => void;
      onError?: (err: any) => void;
    }
  ): Promise<SpeechQueueItem | null> {
    if (!voiceSettings.voiceOutputEnabled || !voiceSettings.autoPlayback) {
      return null;
    }

    // Deduplication by stable eventId
    if (options?.eventId) {
      if (this.announcedEventKeys.has(options.eventId)) {
        return null;
      }
      this.announcedEventKeys.add(options.eventId);
    }

    const cleanText = normalizeTextForSpeech(text);
    if (!cleanText || !cleanText.trim()) {
      return null;
    }

    const item: SpeechQueueItem = {
      id: `spq-${Date.now()}-${Math.random().toString(36).substring(2, 7)}`,
      eventId: options?.eventId,
      text: cleanText,
      priority,
      taskId,
      approvalId: options?.approvalId,
      timestamp: Date.now(),
      metadata,
      audioBase64: options?.audioBase64,
      onStart: options?.onStart,
      onComplete: options?.onComplete,
      onError: options?.onError,
    };

    // Stale Progress Pruning: discard older unplayed PROGRESS updates for this task
    if (priority === NarrationPriority.PROGRESS) {
      this.queue = this.queue.filter(
        (q) => !(q.taskId === taskId && q.priority === NarrationPriority.PROGRESS)
      );
    }

    // Preemption Check:
    // 1. High priority (CRITICAL/APPROVAL) preempts lower priority (PROGRESS/FINAL_RESPONSE)
    // 2. An APPROVAL_DECISION preempts its matching APPROVAL_REQUIRED request
    const shouldPreempt =
      this.currentItem !== null &&
      (
        (this.currentItem.priority > priority && priority <= NarrationPriority.APPROVAL) ||
        (options?.approvalId && this.currentItem.approvalId === options.approvalId)
      );

    if (shouldPreempt) {
      const preempted = this.currentItem!;
      this.activeSequenceId++;
      this.stopCurrentAudio();
      this.callbacks.onPreempt?.(preempted, item);
      // Preempting item runs immediately at the front of the queue
      this.queue.unshift(item);
      this.isProcessing = false;
      this.processQueue(voiceSettings);
    } else {
      // Prioritized Insertion: lower number = higher priority
      const insertIndex = this.queue.findIndex((q) => q.priority > priority);
      if (insertIndex === -1) {
        this.queue.push(item);
      } else {
        this.queue.splice(insertIndex, 0, item);
      }
    }

    // Process queue if not actively processing
    if (!this.isProcessing) {
      this.processQueue(voiceSettings);
    }

    return item;
  }

  /**
   * Enqueues pre-synthesized audio (e.g. from full-response streaming) through the single audio manager.
   */
  public async enqueuePreSynthesized(
    audioBase64: string,
    text: string,
    priority: NarrationPriority,
    taskId: string,
    voiceSettings: VoiceSettings,
    callbacks?: {
      onStart?: () => void;
      onComplete?: () => void;
      onError?: (err: any) => void;
    }
  ): Promise<SpeechQueueItem | null> {
    return this.enqueue(
      text,
      priority,
      taskId,
      voiceSettings,
      { isPreSynthesized: true },
      {
        audioBase64,
        onStart: callbacks?.onStart,
        onComplete: callbacks?.onComplete,
        onError: callbacks?.onError,
      }
    );
  }

  /**
   * Interrupts currently playing audio and advances sequence to discard pending callbacks.
   */
  public interrupt(_reason: string = 'Operator or event interruption'): void {
    this.activeSequenceId++;
    this.stopCurrentAudio();
    if (this.queue.length === 0) {
      this.isProcessing = false;
      this.callbacks.onQueueDrained?.();
    }
  }

  /**
   * Cancel all pending and playing utterances for a specific task ID.
   */
  public cancelTask(taskId: string): void {
    this.queue = this.queue.filter((q) => q.taskId !== taskId);

    if (this.currentItem && this.currentItem.taskId === taskId) {
      this.activeSequenceId++;
      this.stopCurrentAudio();
    }

    if (this.queue.length === 0) {
      this.isProcessing = false;
      this.callbacks.onQueueDrained?.();
    }
  }

  /**
   * Cancel all pending and playing utterances for a specific approval ID.
   */
  public cancelApproval(approvalId: string): void {
    this.queue = this.queue.filter((q) => q.approvalId !== approvalId);

    if (this.currentItem && this.currentItem.approvalId === approvalId) {
      const cancelled = this.currentItem;
      this.activeSequenceId++;
      this.stopCurrentAudio();
      this.callbacks.onPreempt?.(cancelled, cancelled);
      this.isProcessing = false;
    }

    if (this.queue.length === 0) {
      this.isProcessing = false;
      this.callbacks.onQueueDrained?.();
    }
  }

  /**
   * Handles user approval decision: immediately stops obsolete approval request speech
   * and enqueues decision announcement with priority.
   */
  public async onApprovalDecision(
    approvalId: string,
    approved: boolean,
    voiceSettings: VoiceSettings,
    taskId?: string
  ): Promise<SpeechQueueItem | null> {
    // 1. Immediately cancel/interrupt obsolete request announcements for this approval
    this.cancelApproval(approvalId);

    // 2. Announce decision
    const spoken = approved
      ? 'Authorization received. Proceeding.'
      : 'Understood. I will not perform that action.';

    const dedupKey = `approval:${approvalId}:decision`;
    return this.enqueue(
      spoken,
      NarrationPriority.APPROVAL,
      taskId || approvalId,
      voiceSettings,
      { approvalId, approved },
      {
        eventId: dedupKey,
        approvalId,
      }
    );
  }

  /**
   * Immediately stops speech, purges entire queue, and resets playback state.
   */
  public stopAll(): void {
    this.activeSequenceId++;
    this.queue = [];
    this.stopCurrentAudio();
    this.isProcessing = false;
    this.callbacks.onQueueDrained?.();
  }

  private stopCurrentAudio(): void {
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
    this.currentItem = null;
  }

  /**
   * Process the next utterance in the prioritized queue.
   */
  private async processQueue(voiceSettings: VoiceSettings): Promise<void> {
    if (this.queue.length === 0) {
      this.isProcessing = false;
      this.callbacks.onQueueDrained?.();
      return;
    }

    this.isProcessing = true;
    const item = this.queue.shift()!;
    this.currentItem = item;
    const currentSeq = ++this.activeSequenceId;

    try {
      // 1. Synthesize audio on-demand if not pre-synthesized
      let audioBase64 = item.audioBase64;
      if (!audioBase64) {
        const resp = await synthesizeSpeech({
          text: item.text,
          profile_id: voiceSettings.activeProfileId || undefined,
          voice_id: voiceSettings.selectedVoiceId || undefined,
          rate: voiceSettings.speakingRate,
          volume: voiceSettings.volume,
          pitch: voiceSettings.pitch,
          delivery_profile: voiceSettings.deliveryProfile || 'relaxed',
        });

        // Sequence validity check: discard if interrupted during synthesis
        if (currentSeq !== this.activeSequenceId) {
          return;
        }

        audioBase64 = resp.audio_base64;
      }

      if (!audioBase64) {
        this.currentItem = null;
        if (currentSeq === this.activeSequenceId) {
          this.processQueue(voiceSettings);
        }
        return;
      }

      // 2. Play audio stream through authoritative single audio channel
      await this.playAudio(audioBase64, item, currentSeq, voiceSettings);
    } catch (err: any) {
      console.warn(`[SpeechQueue] Synthesis or playback error for item '${item.id}':`, err);
      item.onError?.(err);
      this.callbacks.onError?.(err, item);
      this.currentItem = null;
      if (currentSeq === this.activeSequenceId) {
        this.processQueue(voiceSettings);
      }
    }
  }

  private playAudio(
    audioBase64: string,
    item: SpeechQueueItem,
    seqId: number,
    voiceSettings: VoiceSettings
  ): Promise<void> {
    return new Promise((resolve) => {
      const audioUrl = `data:audio/wav;base64,${audioBase64}`;
      const audio = new Audio(audioUrl);
      this.currentAudio = audio;

      const volumeLevel =
        typeof voiceSettings.volume === 'number'
          ? Math.max(0, Math.min(100, voiceSettings.volume)) / 100
          : 1.0;
      audio.volume = volumeLevel;

      let hasStarted = false;
      const onStart = () => {
        if (!hasStarted && seqId === this.activeSequenceId) {
          hasStarted = true;
          item.onStart?.();
          this.callbacks.onPlaybackStart?.(item);
        }
      };

      const cleanup = () => {
        audio.onplay = null;
        audio.onended = null;
        audio.onerror = null;
        audio.removeEventListener('playing', onStart);
        audio.removeEventListener('ended', onEnded);
        audio.removeEventListener('error', onError);
        if (this.currentAudio === audio) {
          this.currentAudio = null;
        }
        if (this.currentItem === item) {
          this.currentItem = null;
        }
      };

      const onEnded = () => {
        cleanup();
        if (seqId === this.activeSequenceId) {
          item.onComplete?.();
          this.callbacks.onPlaybackComplete?.(item);
          // Advance to next queue item
          this.processQueue(voiceSettings);
        }
        resolve();
      };

      const onError = (e: any) => {
        cleanup();
        if (seqId === this.activeSequenceId) {
          console.warn('[SpeechQueue] Audio playback error:', e);
          item.onError?.(e);
          this.callbacks.onError?.(e, item);
          this.processQueue(voiceSettings);
        }
        resolve();
      };

      audio.onplay = onStart;
      audio.onended = onEnded;
      audio.onerror = onError;
      audio.addEventListener('playing', onStart);
      audio.addEventListener('ended', onEnded);
      audio.addEventListener('error', onError);

      const playPromise = audio.play();
      if (playPromise && typeof playPromise.catch === 'function') {
        playPromise.catch((err) => {
          onError(err);
        });
      }
    });
  }
}

// Global authoritative singleton instance
export const speechQueue = new PrioritizedSpeechQueue();
