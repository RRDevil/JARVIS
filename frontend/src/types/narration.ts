/**
 * Type definitions for J.A.R.V.I.S. Task Narration Subsystem (Phase 5.3).
 */

export type TaskLifecycleEventType =
  | 'TASK_RECEIVED'
  | 'TASK_ACKNOWLEDGED'
  | 'PLANNING_STARTED'
  | 'PLANNING_COMPLETED'
  | 'ACTION_STARTED'
  | 'ACTION_COMPLETED'
  | 'APPROVAL_REQUIRED'
  | 'APPROVAL_GRANTED'
  | 'APPROVAL_DENIED'
  | 'WAITING_FOR_USER'
  | 'RECOVERY_STARTED'
  | 'ACTION_FAILED'
  | 'TASK_COMPLETED'
  | 'TASK_FAILED'
  | 'TASK_CANCELLED';

export enum NarrationPriority {
  CRITICAL = 1,        // Safety warnings, critical errors
  APPROVAL = 2,        // Approval requests and operator decisions
  ACKNOWLEDGMENT = 3,  // Immediate task receipt acknowledgment
  PROGRESS = 4,        // Intermediate execution milestones
  PREVIEW = 5,         // Voice preview / testing in settings
  FINAL_RESPONSE = 6,  // Conversational final responses
}

export interface TaskLifecycleEvent {
  task_id: string;
  event_id?: string;
  approval_id?: string | null;
  event_type: TaskLifecycleEventType;
  action_or_app?: string | null;
  timestamp?: string;
  task_state?: string;
  progress_info?: Record<string, any> | null;
  is_narratable?: boolean;
  narration_text?: string | null;
  priority?: NarrationPriority;
}

export interface NarrationSettings {
  enabled: boolean;
  progressIntervalSeconds: number;
  acknowledgeTasks: boolean;
  announceApprovals: boolean;
  announceErrors: boolean;
  announceProgress: boolean;
  announceCompletion: boolean;
}

export const DEFAULT_NARRATION_SETTINGS: NarrationSettings = {
  enabled: true,
  progressIntervalSeconds: 8.0,
  acknowledgeTasks: true,
  announceApprovals: true,
  announceErrors: true,
  announceProgress: true,
  announceCompletion: true,
};
