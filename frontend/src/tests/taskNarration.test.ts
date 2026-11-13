import { describe, it, expect, vi, beforeEach } from 'vitest';
import { NarrationPriority } from '../types/narration';
import { DEFAULT_VOICE_SETTINGS, VoiceSettings } from '../types/settings';
import { PrioritizedSpeechQueue } from '../services/speechQueue';
import { TaskNarrationCoordinator } from '../services/taskNarration';

vi.mock('../services/api', () => ({
  synthesizeSpeech: vi.fn().mockResolvedValue({
    audio_base64: 'UklGRigAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQAAAAA=',
    duration_seconds: 1.2,
    provider_used: 'piper',
  }),
}));

describe('Task Narration & Prioritized Speech Queue Subsystem (Phase 5.3)', () => {
  let queue: PrioritizedSpeechQueue;
  let coordinator: TaskNarrationCoordinator;
  let voiceSettings: VoiceSettings;

  beforeEach(() => {
    vi.clearAllMocks();
    queue = new PrioritizedSpeechQueue();
    coordinator = new TaskNarrationCoordinator();
    voiceSettings = {
      ...DEFAULT_VOICE_SETTINGS,
      voiceOutputEnabled: true,
      autoPlayback: true,
      narration: {
        enabled: true,
        progressIntervalSeconds: 2.0,
        acknowledgeTasks: true,
        announceApprovals: true,
        announceErrors: true,
        announceProgress: true,
        announceCompletion: true,
      },
    };
  });

  describe('PrioritizedSpeechQueue', () => {
    it('enforces priority ordering across queue items', async () => {
      // Stub playAudio to prevent browser Audio element dependency during unit queue tests
      (queue as any).playAudio = vi.fn().mockImplementation(() => new Promise(() => {}));

      // Enqueue lower priority first, then higher priority
      await queue.enqueue('Progress update', NarrationPriority.PROGRESS, 'task-1', voiceSettings);
      await queue.enqueue('Conversational summary', NarrationPriority.FINAL_RESPONSE, 'task-1', voiceSettings);
      await queue.enqueue('Security alert', NarrationPriority.CRITICAL, 'task-1', voiceSettings);
      await queue.enqueue('Approval prompt', NarrationPriority.APPROVAL, 'task-1', voiceSettings);

      const items = (queue as any).queue;
      // After shifting the first active item, remaining queue must be ordered by priority (lower number first)
      for (let i = 0; i < items.length - 1; i++) {
        expect(items[i].priority).toBeLessThanOrEqual(items[i + 1].priority);
      }
    });

    it('prunes stale progress updates for the same task when a newer progress update arrives', async () => {
      (queue as any).playAudio = vi.fn().mockImplementation(() => new Promise(() => {}));

      // First item becomes active
      await queue.enqueue('Active item', NarrationPriority.ACKNOWLEDGMENT, 'task-1', voiceSettings);

      // Now enqueue two progress updates for task-1
      await queue.enqueue('Old progress update', NarrationPriority.PROGRESS, 'task-1', voiceSettings);
      await queue.enqueue('Fresh progress update', NarrationPriority.PROGRESS, 'task-1', voiceSettings);

      const remainingQueue = (queue as any).queue;
      const progressItems = remainingQueue.filter(
        (q: any) => q.taskId === 'task-1' && q.priority === NarrationPriority.PROGRESS
      );
      // Only the newest progress update should remain
      expect(progressItems.length).toBe(1);
      expect(progressItems[0].text).toBe('Fresh progress update');
    });

    it('cancels all queued speech for a specific task ID', async () => {
      (queue as any).playAudio = vi.fn().mockImplementation(() => new Promise(() => {}));

      await queue.enqueue('Task 1 prompt', NarrationPriority.ACKNOWLEDGMENT, 'task-1', voiceSettings);
      await queue.enqueue('Task 1 progress', NarrationPriority.PROGRESS, 'task-1', voiceSettings);
      await queue.enqueue('Task 2 prompt', NarrationPriority.ACKNOWLEDGMENT, 'task-2', voiceSettings);

      queue.cancelTask('task-1');

      const remaining = (queue as any).queue;
      expect(remaining.some((q: any) => q.taskId === 'task-1')).toBe(false);
      expect(remaining.some((q: any) => q.taskId === 'task-2')).toBe(true);
    });

    it('immediately halts speech and purges queue on stopAll', async () => {
      (queue as any).playAudio = vi.fn().mockImplementation(() => new Promise(() => {}));

      await queue.enqueue('Item 1', NarrationPriority.PROGRESS, 'task-1', voiceSettings);
      await queue.enqueue('Item 2', NarrationPriority.APPROVAL, 'task-1', voiceSettings);

      queue.stopAll();

      expect((queue as any).queue.length).toBe(0);
      expect((queue as any).currentItem).toBeNull();
      expect(queue.isSpeaking()).toBe(false);
    });
  });

  describe('TaskNarrationCoordinator', () => {
    it('formulates immediate natural acknowledgment for varied user requests', async () => {
      // 1. Browser & Navigation
      const ack1 = await coordinator.acknowledgeTask(
        'Open Opera GX and go to Instagram',
        'task-nav',
        voiceSettings
      );
      expect(ack1).not.toBeNull();
      expect(ack1?.event_type).toBe('TASK_ACKNOWLEDGED');
      expect(ack1?.narration_text).toContain('Instagram');

      // 2. Desktop Application
      const ack2 = await coordinator.acknowledgeTask(
        'Launch Notepad for me please',
        'task-app',
        voiceSettings
      );
      expect(ack2?.narration_text).toContain('Notepad');

      // 3. Grounded Clicking
      const ack3 = await coordinator.acknowledgeTask(
        'Click the second video on screen',
        'task-click',
        voiceSettings
      );
      expect(ack3?.narration_text).toContain('Locating');
    });

    it('suppresses acknowledgment for internal continuation prompts', async () => {
      const ack = await coordinator.acknowledgeTask(
        "[SYSTEM NOTIFICATION: The operator approved and executed 'browser.navigate']",
        'task-sys',
        voiceSettings
      );
      expect(ack).toBeNull();
    });

    it('handles approval required announcements with priority 2', async () => {
      const enqueueSpy = vi.spyOn((coordinator as any), 'handleLifecycleEvent');

      await coordinator.announceApprovalRequired(
        "Navigate to 'https://www.instagram.com' in Opera GX",
        'task-appr',
        voiceSettings
      );

      expect(enqueueSpy).toHaveBeenCalled();
      const calledEvent = enqueueSpy.mock.calls[0][0] as any;
      expect(calledEvent.event_type).toBe('APPROVAL_REQUIRED');
      expect(calledEvent.priority).toBe(NarrationPriority.APPROVAL);
      expect(calledEvent.narration_text).toContain('permission');
      expect(calledEvent.narration_text).toContain('Instagram');
    });

    it('handles approval decisions (granted / denied)', async () => {
      const enqueueSpy = vi.spyOn((coordinator as any), 'handleLifecycleEvent');

      // Granted
      await coordinator.announceApprovalDecision(true, 'task-dec-1', voiceSettings);
      const grantEvent = enqueueSpy.mock.calls[0][0] as any;
      expect(grantEvent.event_type).toBe('APPROVAL_GRANTED');
      expect(grantEvent.narration_text).toContain('Authorization received');

      // Denied
      await coordinator.announceApprovalDecision(false, 'task-dec-2', voiceSettings);
      const denyEvent = enqueueSpy.mock.calls[1][0] as any;
      expect(denyEvent.event_type).toBe('APPROVAL_DENIED');
      expect(denyEvent.narration_text).toContain('will not perform');
    });

    it('respects narration disabled toggle', async () => {
      voiceSettings.narration!.enabled = false;

      const ack = await coordinator.acknowledgeTask('Open Opera GX', 'task-off', voiceSettings);
      expect(ack).toBeNull();

      const handled = await coordinator.handleLifecycleEvent(
        {
          task_id: 'task-off',
          event_type: 'ACTION_STARTED',
          narration_text: 'I am opening Opera GX',
          is_narratable: true,
        },
        voiceSettings
      );
      expect(handled).toBe(false);
    });
  });
});
