/**
 * JARVIS Assistant Presentation States and Transitions.
 */

export type AssistantState =
  | 'IDLE'
  | 'LISTENING'
  | 'THINKING'
  | 'RESPONDING'
  | 'SPEAKING'
  | 'EXECUTING'
  | 'AWAITING_APPROVAL'
  | 'ERROR';

export interface StateMetadata {
  label: string;
  code: AssistantState;
  description: string;
  color: string;
  glowColor: string;
  pulseRate: 'slow' | 'medium' | 'fast' | 'urgent';
  ringRotationSpeed: 'normal' | 'fast' | 'reverse' | 'static';
}

export const ASSISTANT_STATE_META: Record<AssistantState, StateMetadata> = {
  IDLE: {
    label: 'SYSTEM STANDBY',
    code: 'IDLE',
    description: 'Awaiting user voice or prompt input',
    color: '#00e5ff',
    glowColor: 'rgba(0, 229, 255, 0.45)',
    pulseRate: 'slow',
    ringRotationSpeed: 'normal',
  },
  LISTENING: {
    label: 'AUDIO CAPTURE ACTIVE',
    code: 'LISTENING',
    description: 'Receiving voice stream from primary microphone',
    color: '#38bdf8',
    glowColor: 'rgba(56, 189, 248, 0.6)',
    pulseRate: 'medium',
    ringRotationSpeed: 'normal',
  },
  THINKING: {
    label: 'COGNITIVE PROCESSING',
    code: 'THINKING',
    description: 'Evaluating user query and synthesizing response plan',
    color: '#818cf8',
    glowColor: 'rgba(129, 140, 248, 0.7)',
    pulseRate: 'fast',
    ringRotationSpeed: 'fast',
  },
  RESPONDING: {
    label: 'SPEECH & TEXT SYNTHESIS',
    code: 'RESPONDING',
    description: 'Streaming response tokens and generating audio',
    color: '#2dd4bf',
    glowColor: 'rgba(45, 212, 191, 0.65)',
    pulseRate: 'medium',
    ringRotationSpeed: 'normal',
  },
  SPEAKING: {
    label: 'VOCAL SYNTHESIS ACTIVE',
    code: 'SPEAKING',
    description: 'Audible speech playback in progress through host audio device',
    color: '#22d3ee',
    glowColor: 'rgba(34, 211, 238, 0.75)',
    pulseRate: 'medium',
    ringRotationSpeed: 'normal',
  },
  EXECUTING: {
    label: 'SYSTEM ACTION EXECUTION',
    code: 'EXECUTING',
    description: 'Running validated tool inside OS sandbox',
    color: '#fbbf24',
    glowColor: 'rgba(251, 191, 36, 0.65)',
    pulseRate: 'fast',
    ringRotationSpeed: 'fast',
  },
  AWAITING_APPROVAL: {
    label: 'AUTHORIZATION REQUIRED',
    code: 'AWAITING_APPROVAL',
    description: 'Consequential action paused pending explicit user approval',
    color: '#f97316',
    glowColor: 'rgba(249, 115, 22, 0.8)',
    pulseRate: 'urgent',
    ringRotationSpeed: 'reverse',
  },
  ERROR: {
    label: 'SYSTEM FAULT',
    code: 'ERROR',
    description: 'Operation failed or security policy violated',
    color: '#ef4444',
    glowColor: 'rgba(239, 68, 68, 0.8)',
    pulseRate: 'urgent',
    ringRotationSpeed: 'static',
  },
};

/**
 * Validates whether transitioning from currentState to nextState is permitted.
 */
export function isValidStateTransition(current: AssistantState, next: AssistantState): boolean {
  if (current === next) return true;
  // Error can be transitioned into from any state
  if (next === 'ERROR') return true;
  // From Error, we can only reset to Idle
  if (current === 'ERROR') return next === 'IDLE';

  switch (current) {
    case 'IDLE':
      return ['LISTENING', 'THINKING', 'EXECUTING', 'SPEAKING'].includes(next);
    case 'LISTENING':
      return ['THINKING', 'IDLE'].includes(next);
    case 'THINKING':
      return ['RESPONDING', 'SPEAKING', 'EXECUTING', 'AWAITING_APPROVAL', 'IDLE'].includes(next);
    case 'RESPONDING':
      return ['IDLE', 'SPEAKING', 'LISTENING', 'EXECUTING'].includes(next);
    case 'SPEAKING':
      return ['IDLE', 'LISTENING', 'THINKING'].includes(next);
    case 'EXECUTING':
      return ['THINKING', 'RESPONDING', 'SPEAKING', 'AWAITING_APPROVAL', 'IDLE'].includes(next);
    case 'AWAITING_APPROVAL':
      return ['EXECUTING', 'IDLE'].includes(next);
    default:
      return false;
  }
}

