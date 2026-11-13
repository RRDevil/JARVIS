import { describe, it, expect } from 'vitest';
import {
  AssistantState,
  ASSISTANT_STATE_META,
  isValidStateTransition,
} from '../types/assistantState';

describe('Assistant State Model & Transitions', () => {
  const allStates: AssistantState[] = [
    'IDLE',
    'LISTENING',
    'THINKING',
    'RESPONDING',
    'EXECUTING',
    'AWAITING_APPROVAL',
    'ERROR',
  ];

  it('defines metadata for all seven presentation states', () => {
    allStates.forEach((state) => {
      const meta = ASSISTANT_STATE_META[state];
      expect(meta).toBeDefined();
      expect(meta.label).toBeTruthy();
      expect(meta.color).toMatch(/^#[0-9a-fA-F]{6}$/);
      expect(meta.glowColor).toBeTruthy();
      expect(['slow', 'medium', 'fast', 'urgent']).toContain(meta.pulseRate);
      expect(['normal', 'fast', 'reverse', 'static']).toContain(meta.ringRotationSpeed);
    });
  });

  it('permits valid linear state progression', () => {
    // Normal conversation lifecycle
    expect(isValidStateTransition('IDLE', 'LISTENING')).toBe(true);
    expect(isValidStateTransition('LISTENING', 'THINKING')).toBe(true);
    expect(isValidStateTransition('THINKING', 'RESPONDING')).toBe(true);
    expect(isValidStateTransition('RESPONDING', 'IDLE')).toBe(true);
  });

  it('permits action execution and approval transitions', () => {
    expect(isValidStateTransition('THINKING', 'AWAITING_APPROVAL')).toBe(true);
    expect(isValidStateTransition('AWAITING_APPROVAL', 'EXECUTING')).toBe(true);
    expect(isValidStateTransition('EXECUTING', 'RESPONDING')).toBe(true);
    expect(isValidStateTransition('AWAITING_APPROVAL', 'IDLE')).toBe(true); // User rejection returns to idle
  });

  it('permits transitioning to ERROR from any state, and only from ERROR to IDLE', () => {
    allStates.forEach((st) => {
      expect(isValidStateTransition(st, 'ERROR')).toBe(true);
    });

    expect(isValidStateTransition('ERROR', 'IDLE')).toBe(true);
    expect(isValidStateTransition('ERROR', 'LISTENING')).toBe(false);
    expect(isValidStateTransition('ERROR', 'EXECUTING')).toBe(false);
  });

  it('rejects illegal state jumps', () => {
    expect(isValidStateTransition('LISTENING', 'EXECUTING')).toBe(false);
    expect(isValidStateTransition('RESPONDING', 'AWAITING_APPROVAL')).toBe(false);
  });

  it('allows transitioning to the same state (idempotent)', () => {
    allStates.forEach((st) => {
      expect(isValidStateTransition(st, st)).toBe(true);
    });
  });
});

