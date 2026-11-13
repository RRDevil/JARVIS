/**
 * J.A.R.V.I.S. Speech Timing Controller & Conversational Delivery Profiles.
 *
 * Computes natural structural pauses and acoustic synthesis parameters based on
 * conversational boundary structures (paragraphs, sentences, clauses) and delivery style presets.
 */

export type DeliveryProfile = 'relaxed' | 'conversational' | 'formal';

export type BoundaryType = 'paragraph' | 'question' | 'exclamation' | 'sentence' | 'clause' | 'neutral';

export interface DeliveryProfileConfig {
  id: DeliveryProfile;
  name: string;
  description: string;
  lengthScale: number;
  noiseScale: number;
  noiseWScale: number;
  sentencePauseMs: number;
  paragraphPauseMs: number;
  clausePauseMs: number;
}

export const DELIVERY_PROFILES: Record<DeliveryProfile, DeliveryProfileConfig> = {
  relaxed: {
    id: 'relaxed',
    name: 'Relaxed (Default)',
    description: 'Calm, steady, comfortable pacing with grounded pitch and smooth sentence flow.',
    lengthScale: 1.06,
    noiseScale: 0.333,
    noiseWScale: 0.50,
    sentencePauseMs: 280,
    paragraphPauseMs: 460,
    clausePauseMs: 40,
  },
  conversational: {
    id: 'conversational',
    name: 'Conversational',
    description: 'Natural everyday speaking rhythm with balanced inflection and fluid transitions.',
    lengthScale: 1.00,
    noiseScale: 0.450,
    noiseWScale: 0.60,
    sentencePauseMs: 200,
    paragraphPauseMs: 360,
    clausePauseMs: 30,
  },
  formal: {
    id: 'formal',
    name: 'Formal',
    description: 'Measured, deliberate cadence with clear articulation and structured pauses.',
    lengthScale: 1.12,
    noiseScale: 0.280,
    noiseWScale: 0.40,
    sentencePauseMs: 350,
    paragraphPauseMs: 550,
    clausePauseMs: 60,
  },
};

export class SpeechTimingController {
  private activeProfile: DeliveryProfile = 'relaxed';

  public setDeliveryProfile(profile: DeliveryProfile): void {
    if (DELIVERY_PROFILES[profile]) {
      this.activeProfile = profile;
    }
  }

  public getActiveProfile(): DeliveryProfile {
    return this.activeProfile;
  }

  public getProfileConfig(profile?: DeliveryProfile): DeliveryProfileConfig {
    const target = profile || this.activeProfile;
    return DELIVERY_PROFILES[target] || DELIVERY_PROFILES.relaxed;
  }

  /**
   * Computes the natural pause in milliseconds to observe AFTER speaking a segment.
   */
  public calculatePauseDurationMs(boundaryType: BoundaryType, profile?: DeliveryProfile): number {
    const config = this.getProfileConfig(profile);

    switch (boundaryType) {
      case 'paragraph':
        return config.paragraphPauseMs;
      case 'question':
      case 'exclamation':
      case 'sentence':
        return config.sentencePauseMs;
      case 'clause':
        return config.clausePauseMs;
      case 'neutral':
      default:
        return 0;
    }
  }

  /**
   * Detects the boundary type of a text segment based on its raw terminating characters.
   */
  public detectBoundaryType(rawSegment: string): BoundaryType {
    if (!rawSegment) return 'neutral';
    const trimmed = rawSegment.trim();

    if (rawSegment.includes('\n\n')) {
      return 'paragraph';
    }
    if (trimmed.endsWith('?')) {
      return 'question';
    }
    if (trimmed.endsWith('!')) {
      return 'exclamation';
    }
    if (trimmed.endsWith('.')) {
      return 'sentence';
    }
    if (trimmed.endsWith(',') || trimmed.endsWith(';') || trimmed.endsWith(':') || trimmed.endsWith('—')) {
      return 'clause';
    }
    return 'neutral';
  }
}

// Global Singleton
export const speechTiming = new SpeechTimingController();

