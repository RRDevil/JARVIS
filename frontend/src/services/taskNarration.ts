/**
 * Centralized Task Narration Coordinator for J.A.R.V.I.S. (Phase 5.3).
 *
 * Coordinates proactive spoken progress, immediate task acknowledgments,
 * approval requests, errors, and completions through the Prioritized Speech Queue.
 */

import {
  NarrationPriority,
  NarrationSettings,
  TaskLifecycleEvent,
} from '../types/narration';
import { VoiceSettings } from '../types/settings';
import { speechQueue } from './speechQueue';

export interface NarrationCallbacks {
  onNarrationStart?: (event: TaskLifecycleEvent) => void;
  onNarrationComplete?: (event: TaskLifecycleEvent) => void;
  onError?: (err: any) => void;
}

export class TaskNarrationCoordinator {
  private callbacks: NarrationCallbacks = {};
  private lastProgressNarrationTime: Record<string, number> = {};
  private lastActionKey: Record<string, string> = {};
  private announcedApprovals = new Set<string>();

  constructor(callbacks: NarrationCallbacks = {}) {
    this.callbacks = callbacks;
    void this.callbacks;
  }

  public setCallbacks(callbacks: NarrationCallbacks): void {
    this.callbacks = callbacks;
  }

  public clearDeduplicationRegistry(): void {
    this.announcedApprovals.clear();
    speechQueue.clearDeduplicationRegistry();
  }

  /**
   * Immediately acknowledges a user task request before waiting for LLM completion.
   */
  public async acknowledgeTask(
    userPrompt: string,
    taskId: string,
    voiceSettings: VoiceSettings
  ): Promise<TaskLifecycleEvent | null> {
    const narrationConfig: NarrationSettings = voiceSettings.narration || {
      enabled: true,
      progressIntervalSeconds: 8.0,
      acknowledgeTasks: true,
      announceApprovals: true,
      announceErrors: true,
      announceProgress: true,
      announceCompletion: true,
    };

    if (!narrationConfig.enabled || !narrationConfig.acknowledgeTasks) {
      return null;
    }

    const cleanPrompt = userPrompt.trim().toLowerCase();
    // Do not acknowledge internal continuation prompts
    if (cleanPrompt.startsWith('[system') || cleanPrompt.startsWith('[approval') || !cleanPrompt) {
      return null;
    }

    const ackText = this.formulateAcknowledgment(userPrompt);
    const event: TaskLifecycleEvent = {
      task_id: taskId,
      event_type: 'TASK_ACKNOWLEDGED',
      task_state: 'THINKING',
      is_narratable: true,
      narration_text: ackText,
      priority: NarrationPriority.ACKNOWLEDGMENT,
      progress_info: { prompt: userPrompt.substring(0, 80) },
    };

    await speechQueue.enqueue(ackText, NarrationPriority.ACKNOWLEDGMENT, taskId, voiceSettings, {
      eventType: 'TASK_ACKNOWLEDGED',
    });

    return event;
  }

  /**
   * Evaluates incoming SSE or client-side lifecycle event and enqueues narration.
   */
  public async handleLifecycleEvent(
    event: TaskLifecycleEvent,
    voiceSettings: VoiceSettings
  ): Promise<boolean> {
    const narrationConfig: NarrationSettings = voiceSettings.narration || {
      enabled: true,
      progressIntervalSeconds: 8.0,
      acknowledgeTasks: true,
      announceApprovals: true,
      announceErrors: true,
      announceProgress: true,
      announceCompletion: true,
    };

    if (!narrationConfig.enabled || !event.is_narratable || !event.narration_text) {
      return false;
    }

    // Filter by specific category flags
    switch (event.event_type) {
      case 'TASK_ACKNOWLEDGED':
        if (!narrationConfig.acknowledgeTasks) return false;
        break;

      case 'APPROVAL_REQUIRED':
        if (!narrationConfig.announceApprovals) return false;
        // Strict Deduplication: at most ONE spoken announcement per approval ID
        if (event.approval_id) {
          if (this.announcedApprovals.has(event.approval_id)) return false;
          this.announcedApprovals.add(event.approval_id);
        }
        break;

      case 'APPROVAL_GRANTED':
      case 'APPROVAL_DENIED':
        if (!narrationConfig.announceApprovals) return false;
        await speechQueue.onApprovalDecision(
          event.approval_id || event.task_id,
          event.event_type === 'APPROVAL_GRANTED',
          voiceSettings,
          event.task_id
        );
        return true;

      case 'ACTION_FAILED':
      case 'RECOVERY_STARTED':
      case 'TASK_FAILED':
        if (!narrationConfig.announceErrors) return false;
        break;

      case 'ACTION_STARTED':
      case 'ACTION_COMPLETED':
      case 'PLANNING_STARTED':
        if (!narrationConfig.announceProgress) return false;
        // Check progress throttling
        const now = Date.now();
        const lastTime = this.lastProgressNarrationTime[event.task_id] || 0;
        const intervalMs = (narrationConfig.progressIntervalSeconds || 8.0) * 1000;
        if (now - lastTime < intervalMs && event.action_or_app === this.lastActionKey[event.task_id]) {
          return false;
        }
        this.lastProgressNarrationTime[event.task_id] = now;
        if (event.action_or_app) {
          this.lastActionKey[event.task_id] = event.action_or_app;
        }
        break;

      case 'TASK_COMPLETED':
        if (!narrationConfig.announceCompletion) return false;
        break;

      case 'TASK_CANCELLED':
        this.cancelTask(event.task_id);
        break;
    }

    const priority = event.priority || NarrationPriority.PROGRESS;
    const eventId = event.event_id || (event.approval_id ? `approval:${event.approval_id}:required` : undefined);
    await speechQueue.enqueue(
      event.narration_text,
      priority,
      event.task_id,
      voiceSettings,
      { eventType: event.event_type, context: event.progress_info?.context },
      {
        eventId,
        approvalId: event.approval_id || undefined,
      }
    );

    return true;
  }

  /**
   * Spoken alert for consequential approval requirement.
   */
  public async announceApprovalRequired(
    actionSummary: string,
    approvalId: string,
    voiceSettings: VoiceSettings,
    taskId?: string
  ): Promise<void> {
    if (this.announcedApprovals.has(approvalId)) {
      return;
    }
    this.announcedApprovals.add(approvalId);

    const clean = actionSummary.replace(/^Execute\s+/i, '').replace(/\s+in Opera GX$/i, '').trim();
    let spoken = `Sir, I need your permission before ${clean}.`;
    if (/navigate|instagram|youtube|google/i.test(clean)) {
      spoken = `Sir, I need your permission before navigating to ${this.extractFriendlyDestination(clean)}.`;
    }

    const event: TaskLifecycleEvent = {
      task_id: taskId || approvalId,
      approval_id: approvalId,
      event_id: `approval:${approvalId}:required`,
      event_type: 'APPROVAL_REQUIRED',
      task_state: 'AWAITING_APPROVAL',
      is_narratable: true,
      narration_text: spoken,
      priority: NarrationPriority.APPROVAL,
    };

    await this.handleLifecycleEvent(event, voiceSettings);
  }

  /**
   * Spoken announcement for approval decision. Immediately interrupts obsolete
   * approval request announcements and speaks decision.
   */
  public async announceApprovalDecision(
    approved: boolean,
    approvalId: string,
    voiceSettings: VoiceSettings,
    taskId?: string
  ): Promise<void> {
    const spoken = approved
      ? 'Authorization received. Proceeding.'
      : 'Understood. I will not perform that action.';

    const event: TaskLifecycleEvent = {
      task_id: taskId || approvalId,
      approval_id: approvalId,
      event_id: `approval:${approvalId}:decision`,
      event_type: approved ? 'APPROVAL_GRANTED' : 'APPROVAL_DENIED',
      task_state: approved ? 'EXECUTING' : 'IDLE',
      is_narratable: true,
      narration_text: spoken,
      priority: NarrationPriority.APPROVAL,
    };

    await this.handleLifecycleEvent(event, voiceSettings);
  }

  public cancelTask(taskId: string): void {
    delete this.lastProgressNarrationTime[taskId];
    delete this.lastActionKey[taskId];
    speechQueue.cancelTask(taskId);
  }

  public stopSpeaking(): void {
    speechQueue.stopAll();
  }

  private formulateAcknowledgment(prompt: string): string {
    const p = prompt.toLowerCase().trim();

    // Destination matching
    let dest: string | null = null;
    if (p.includes('instagram')) dest = 'Instagram';
    else if (p.includes('youtube')) dest = 'YouTube';
    else if (p.includes('reddit')) dest = 'Reddit';
    else if (p.includes('github')) dest = 'GitHub';

    // Application specific
    for (const [key, name] of [
      ['opera', 'Opera GX'],
      ['chrome', 'Chrome'],
      ['word', 'Microsoft Word'],
      ['excel', 'Microsoft Excel'],
      ['powerpoint', 'PowerPoint'],
      ['discord', 'Discord'],
      ['notepad', 'Notepad'],
      ['calculator', 'Calculator'],
      ['terminal', 'Windows Terminal'],
    ]) {
      if (p.includes(key)) {
        if (key === 'opera' || key === 'chrome') {
          if (dest) return `Certainly, sir. Opening ${name} and navigating to ${dest}.`;
          if (/search|navigate|go to|visit/.test(p)) return `Certainly, sir. Opening ${name} and navigating to the page.`;
        }
        return `Certainly, sir. Opening ${name}.`;
      }
    }

    if (dest) {
      return `Certainly, sir. Opening ${dest} in your browser.`;
    }

    if (/navigate|browse|website|search for/.test(p)) {
      return 'Certainly, sir. Navigating to the requested page.';
    }

    if (/open|launch|start/.test(p)) {
      return 'Of course, sir. Opening that now.';
    }

    if (/click|press|select|tap|type into|enter text/.test(p)) {
      return 'On it, sir. Locating the requested element.';
    }

    if (/read the screen|inspect|what is on|look at|capture/.test(p)) {
      return 'Looking into that now, sir. Inspecting the display.';
    }

    if (/document|write|spreadsheet|draft|presentation/.test(p)) {
      return 'Right away. Preparing the workspace.';
    }

    return "Understood, sir. Looking into that for you.";
  }

  private extractFriendlyDestination(summary: string): string {
    const lower = summary.toLowerCase();
    if (lower.includes('instagram')) return 'Instagram';
    if (lower.includes('youtube')) return 'YouTube';
    if (lower.includes('google')) return 'Google';
    if (lower.includes('github')) return 'GitHub';
    const match = summary.match(/https?:\/\/(?:www\.)?([^/'"\s]+)/i);
    return match ? match[1] : 'the requested page';
  }
}

// Global singleton instance
export const taskNarration = new TaskNarrationCoordinator();
