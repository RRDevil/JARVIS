/**
 * Test Suite for Centralized Authoritative Speech Playback Manager & Approval Synchronization.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { PrioritizedSpeechQueue } from '../services/speechQueue';
import { TaskNarrationCoordinator } from '../services/taskNarration';
import { NarrationPriority } from '../types/narration';
import { DEFAULT_VOICE_SETTINGS } from '../types/settings';
import * as api from '../services/api';

vi.mock('../services/api', () => ({
  synthesizeSpeech: vi.fn(),
}));

describe('Authoritative Speech Playback Manager & Approval Synchronization', () => {
  let queue: PrioritizedSpeechQueue;
  let coordinator: TaskNarrationCoordinator;

  beforeEach(() => {
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
        addEventListener(event: string, cb: any) {
          if (event === 'playing') this.onplay = cb;
          if (event === 'ended') this.onended = cb;
          if (event === 'error') this.onerror = cb;
        }
        removeEventListener() {}
      }
    );

    vi.mocked(api.synthesizeSpeech).mockResolvedValue({
      audio_base64: 'UklGRiQAAABXQVZFZm10IBAAAAABAAEARKwAAIhYAQACABAAZGF0YQAAAAA=',
      mime_type: 'audio/wav',
      duration_seconds: 2.0,
      voice_used: 'piper-lessac',
      provider_used: 'piper',
      fallback_applied: false,
    });

    queue = new PrioritizedSpeechQueue();
    coordinator = new TaskNarrationCoordinator();
    coordinator.clearDeduplicationRegistry();
  });

  afterEach(() => {
    queue.stopAll();
    coordinator.stopSpeaking();
    vi.restoreAllMocks();
  });

  it('deduplicates identical speech events by stable eventId', async () => {
    const eventId = 'approval:appr-test-1:required';

    // First enqueue succeeds
    const item1 = await queue.enqueue(
      'Sir, I need your permission before navigating to Instagram.',
      NarrationPriority.APPROVAL,
      'task-1',
      DEFAULT_VOICE_SETTINGS,
      {},
      { eventId, approvalId: 'appr-test-1' }
    );
    expect(item1).not.toBeNull();

    // Second enqueue with the exact same eventId must be deduplicated
    const item2 = await queue.enqueue(
      'Sir, I need your permission before navigating to Instagram.',
      NarrationPriority.APPROVAL,
      'task-1',
      DEFAULT_VOICE_SETTINGS,
      {},
      { eventId, approvalId: 'appr-test-1' }
    );
    expect(item2).toBeNull();
  });

  it('immediately interrupts in-flight approval request announcement when approval is granted', async () => {
    let preemptedItem: any = null;
    queue.setCallbacks({
      onPreempt: (cancelled) => {
        preemptedItem = cancelled;
      },
    });

    // Start playing approval request
    await queue.enqueue(
      'Sir, I need your permission before typing into Notepad.',
      NarrationPriority.APPROVAL,
      'task-2',
      DEFAULT_VOICE_SETTINGS,
      {},
      { eventId: 'approval:appr-2:required', approvalId: 'appr-2' }
    );

    expect(queue.isSpeaking()).toBe(true);
    expect(queue.getCurrentItem()?.approvalId).toBe('appr-2');

    // Operator approves the action: onApprovalDecision must immediately interrupt the request announcement
    const decisionItem = await queue.onApprovalDecision('appr-2', true, DEFAULT_VOICE_SETTINGS, 'task-2');

    expect(decisionItem).not.toBeNull();
    expect(decisionItem?.text).toContain('Authorization received');
    expect(preemptedItem).not.toBeNull();
    expect(preemptedItem.approvalId).toBe('appr-2');
  });

  it('preempts lower-priority progress updates when an approval request arrives', async () => {
    let preemptCount = 0;
    queue.setCallbacks({
      onPreempt: () => {
        preemptCount++;
      },
    });

    // Enqueue progress update (Priority 4)
    await queue.enqueue(
      'Inspecting desktop window...',
      NarrationPriority.PROGRESS,
      'task-3',
      DEFAULT_VOICE_SETTINGS
    );

    expect(queue.getCurrentItem()?.priority).toBe(NarrationPriority.PROGRESS);

    // Urgent approval arrives (Priority 2)
    await queue.enqueue(
      'Sir, I need your permission before launching Terminal.',
      NarrationPriority.APPROVAL,
      'task-3',
      DEFAULT_VOICE_SETTINGS,
      {},
      { eventId: 'approval:appr-3:required', approvalId: 'appr-3' }
    );

    // Lower priority item must have been preempted
    expect(preemptCount).toBe(1);
    expect(queue.getCurrentItem()?.priority).toBe(NarrationPriority.APPROVAL);
  });

  it('discards queued speech and halts active speech on task cancellation', async () => {
    // Enqueue multiple items for task-4
    await queue.enqueue('Starting step 1...', NarrationPriority.PROGRESS, 'task-4', DEFAULT_VOICE_SETTINGS);
    await queue.enqueue('Starting step 2...', NarrationPriority.PROGRESS, 'task-4', DEFAULT_VOICE_SETTINGS);

    expect(queue.isSpeaking()).toBe(true);

    // Cancel task-4
    queue.cancelTask('task-4');

    expect(queue.isSpeaking()).toBe(false);
    expect(queue.getCurrentItem()).toBeNull();
  });

  it('coordinator prevents duplicate spoken announcements for the same approval ID across sources', async () => {
    const approvalId = 'appr-unique-99';

    // Source 1: SSE narration event
    const sseEvent = {
      task_id: 'task-5',
      event_id: `approval:${approvalId}:required`,
      approval_id: approvalId,
      event_type: 'APPROVAL_REQUIRED' as const,
      narration_text: 'Sir, I need your permission.',
      is_narratable: true,
      priority: NarrationPriority.APPROVAL,
    };
    const accepted1 = await coordinator.handleLifecycleEvent(sseEvent, DEFAULT_VOICE_SETTINGS);
    expect(accepted1).toBe(true);

    // Source 2: REST API polling announcing the same approval request
    await coordinator.announceApprovalRequired('Execute action', approvalId, DEFAULT_VOICE_SETTINGS, 'task-5');

    // Second announcement must be blocked by deduplication
    const acceptedDuplicate = await coordinator.handleLifecycleEvent(sseEvent, DEFAULT_VOICE_SETTINGS);
    expect(acceptedDuplicate).toBe(false);
  });

  it('guarantees only one active audio stream is ever speaking at once', async () => {
    // Enqueue item 1 and item 2 rapidly
    await queue.enqueue('First utterance', NarrationPriority.ACKNOWLEDGMENT, 'task-6', DEFAULT_VOICE_SETTINGS);
    await queue.enqueue('Second utterance', NarrationPriority.PROGRESS, 'task-6', DEFAULT_VOICE_SETTINGS);

    // Only First utterance is currently playing; second is in queue
    expect(queue.getCurrentItem()?.text).toContain('First utterance');
  });
});
