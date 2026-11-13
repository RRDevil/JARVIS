import { describe, it, expect } from 'vitest';
import {
  speechTiming,
  DELIVERY_PROFILES,
} from '../services/speechTiming';

describe('SpeechTimingController & Delivery Profiles', () => {
  it('provides all 3 required delivery profiles with tuned prosody parameters', () => {
    expect(DELIVERY_PROFILES.relaxed).toBeDefined();
    expect(DELIVERY_PROFILES.conversational).toBeDefined();
    expect(DELIVERY_PROFILES.formal).toBeDefined();

    // Relaxed (default): calm, steady pitch, low noise
    expect(DELIVERY_PROFILES.relaxed.noiseScale).toBe(0.333);
    expect(DELIVERY_PROFILES.relaxed.noiseWScale).toBe(0.50);
    expect(DELIVERY_PROFILES.relaxed.lengthScale).toBe(1.06);

    // Conversational: balanced rhythm
    expect(DELIVERY_PROFILES.conversational.noiseScale).toBe(0.45);
    expect(DELIVERY_PROFILES.conversational.noiseWScale).toBe(0.60);
    expect(DELIVERY_PROFILES.conversational.lengthScale).toBe(1.00);

    // Formal: deliberate, clear articulation
    expect(DELIVERY_PROFILES.formal.noiseScale).toBe(0.28);
    expect(DELIVERY_PROFILES.formal.noiseWScale).toBe(0.40);
    expect(DELIVERY_PROFILES.formal.lengthScale).toBe(1.12);
  });

  it('detects boundary types from terminating punctuation and whitespace', () => {
    expect(speechTiming.detectBoundaryType('Hello world.\n\nNext section.')).toBe('paragraph');
    expect(speechTiming.detectBoundaryType('How can I help you?')).toBe('question');
    expect(speechTiming.detectBoundaryType('All systems nominal!')).toBe('exclamation');
    expect(speechTiming.detectBoundaryType('Processing your request.')).toBe('sentence');
    expect(speechTiming.detectBoundaryType('However,')).toBe('clause');
    expect(speechTiming.detectBoundaryType('Continuing fragment')).toBe('neutral');
  });

  it('calculates profile-dependent structural pauses', () => {
    // Relaxed pauses
    expect(speechTiming.calculatePauseDurationMs('sentence', 'relaxed')).toBe(280);
    expect(speechTiming.calculatePauseDurationMs('question', 'relaxed')).toBe(280);
    expect(speechTiming.calculatePauseDurationMs('paragraph', 'relaxed')).toBe(460);
    expect(speechTiming.calculatePauseDurationMs('clause', 'relaxed')).toBe(40);
    expect(speechTiming.calculatePauseDurationMs('neutral', 'relaxed')).toBe(0);

    // Conversational pauses
    expect(speechTiming.calculatePauseDurationMs('sentence', 'conversational')).toBe(200);
    expect(speechTiming.calculatePauseDurationMs('paragraph', 'conversational')).toBe(360);

    // Formal pauses
    expect(speechTiming.calculatePauseDurationMs('sentence', 'formal')).toBe(350);
    expect(speechTiming.calculatePauseDurationMs('paragraph', 'formal')).toBe(550);
  });

  it('allows switching the active delivery profile', () => {
    speechTiming.setDeliveryProfile('formal');
    expect(speechTiming.getActiveProfile()).toBe('formal');
    expect(speechTiming.calculatePauseDurationMs('sentence')).toBe(350);

    speechTiming.setDeliveryProfile('relaxed');
    expect(speechTiming.getActiveProfile()).toBe('relaxed');
    expect(speechTiming.calculatePauseDurationMs('sentence')).toBe(280);
  });
});
