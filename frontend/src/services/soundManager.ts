/**
 * JARVIS Futuristic Sound-Cue Synthesizer (Web Audio API).
 *
 * Provides procedural, zero-dependency sound effects for interface events
 * and assistant state transitions without relying on remote or external assets.
 */

export type SoundEvent =
  | 'ACTIVATION'
  | 'DEACTIVATION'
  | 'LISTENING_START'
  | 'LISTENING_STOP'
  | 'RESPONSE_START'
  | 'RESPONSE_COMPLETE'
  | 'APPROVAL_REQUIRED'
  | 'ERROR_OCCURRED'
  | 'CLICK_CUE';

class SoundManager {
  private ctx: AudioContext | null = null;
  private enabled: boolean = true;
  private volume: number = 0.5; // 0.0 to 1.0

  constructor() {
    // AudioContext will be initialized on first user gesture
  }

  public setEnabled(enabled: boolean): void {
    this.enabled = enabled;
  }

  public setVolume(volume0to100: number): void {
    this.volume = Math.max(0, Math.min(1, volume0to100 / 100));
  }

  public isEnabled(): boolean {
    return this.enabled;
  }

  public getVolume(): number {
    return Math.round(this.volume * 100);
  }

  private getAudioContext(): AudioContext | null {
    if (typeof window === 'undefined') return null;
    if (!this.ctx) {
      const AudioCtx = window.AudioContext || (window as any).webkitAudioContext;
      if (AudioCtx) {
        this.ctx = new AudioCtx();
      }
    }
    if (this.ctx && this.ctx.state === 'suspended') {
      this.ctx.resume().catch(() => {});
    }
    return this.ctx;
  }

  public play(event: SoundEvent): void {
    if (!this.enabled || this.volume <= 0) return;

    const ctx = this.getAudioContext();
    if (!ctx) return;

    try {
      const now = ctx.currentTime;
      const masterGain = ctx.createGain();
      masterGain.gain.setValueAtTime(this.volume * 0.15, now);
      masterGain.connect(ctx.destination);

      switch (event) {
        case 'ACTIVATION': {
          // Futuristic triad arpeggio: C5 -> E5 -> G5 -> C6
          const freqs = [523.25, 659.25, 783.99, 1046.5];
          freqs.forEach((freq, idx) => {
            const osc = ctx.createOscillator();
            const gain = ctx.createGain();
            osc.type = 'sine';
            osc.frequency.setValueAtTime(freq, now + idx * 0.06);

            gain.gain.setValueAtTime(0, now + idx * 0.06);
            gain.gain.linearRampToValueAtTime(0.3, now + idx * 0.06 + 0.02);
            gain.gain.exponentialRampToValueAtTime(0.001, now + idx * 0.06 + 0.2);

            osc.connect(gain);
            gain.connect(masterGain);
            osc.start(now + idx * 0.06);
            osc.stop(now + idx * 0.06 + 0.22);
          });
          break;
        }

        case 'DEACTIVATION': {
          // Descending powerdown arpeggio: C6 -> G5 -> E5 -> C5
          const freqs = [1046.5, 783.99, 659.25, 523.25];
          freqs.forEach((freq, idx) => {
            const osc = ctx.createOscillator();
            const gain = ctx.createGain();
            osc.type = 'sine';
            osc.frequency.setValueAtTime(freq, now + idx * 0.06);

            gain.gain.setValueAtTime(0.25, now + idx * 0.06);
            gain.gain.exponentialRampToValueAtTime(0.001, now + idx * 0.06 + 0.2);

            osc.connect(gain);
            gain.connect(masterGain);
            osc.start(now + idx * 0.06);
            osc.stop(now + idx * 0.06 + 0.22);
          });
          break;
        }

        case 'LISTENING_START': {
          // Soft radar frequency upward chirp
          const osc = ctx.createOscillator();
          const gain = ctx.createGain();
          osc.type = 'sine';
          osc.frequency.setValueAtTime(440, now);
          osc.frequency.exponentialRampToValueAtTime(880, now + 0.12);

          gain.gain.setValueAtTime(0.2, now);
          gain.gain.exponentialRampToValueAtTime(0.001, now + 0.18);

          osc.connect(gain);
          gain.connect(masterGain);
          osc.start(now);
          osc.stop(now + 0.2);
          break;
        }

        case 'LISTENING_STOP': {
          // Downward chirp
          const osc = ctx.createOscillator();
          const gain = ctx.createGain();
          osc.type = 'sine';
          osc.frequency.setValueAtTime(880, now);
          osc.frequency.exponentialRampToValueAtTime(440, now + 0.12);

          gain.gain.setValueAtTime(0.2, now);
          gain.gain.exponentialRampToValueAtTime(0.001, now + 0.18);

          osc.connect(gain);
          gain.connect(masterGain);
          osc.start(now);
          osc.stop(now + 0.2);
          break;
        }

        case 'RESPONSE_START': {
          // Subtle dual harmonic pulse
          [587.33, 880].forEach((freq) => {
            const osc = ctx.createOscillator();
            const gain = ctx.createGain();
            osc.type = 'triangle';
            osc.frequency.setValueAtTime(freq, now);

            gain.gain.setValueAtTime(0.15, now);
            gain.gain.exponentialRampToValueAtTime(0.001, now + 0.25);

            osc.connect(gain);
            gain.connect(masterGain);
            osc.start(now);
            osc.stop(now + 0.26);
          });
          break;
        }

        case 'RESPONSE_COMPLETE': {
          // Harmonious double chime
          [659.25, 987.77].forEach((freq, idx) => {
            const osc = ctx.createOscillator();
            const gain = ctx.createGain();
            osc.type = 'sine';
            osc.frequency.setValueAtTime(freq, now + idx * 0.08);

            gain.gain.setValueAtTime(0.25, now + idx * 0.08);
            gain.gain.exponentialRampToValueAtTime(0.001, now + idx * 0.08 + 0.3);

            osc.connect(gain);
            gain.connect(masterGain);
            osc.start(now + idx * 0.08);
            osc.stop(now + idx * 0.08 + 0.32);
          });
          break;
        }

        case 'APPROVAL_REQUIRED': {
          // Amber attention two-tone warning
          [740, 740, 880].forEach((freq, idx) => {
            const osc = ctx.createOscillator();
            const gain = ctx.createGain();
            osc.type = 'square';
            osc.frequency.setValueAtTime(freq, now + idx * 0.12);

            gain.gain.setValueAtTime(0.12, now + idx * 0.12);
            gain.gain.exponentialRampToValueAtTime(0.001, now + idx * 0.12 + 0.1);

            osc.connect(gain);
            gain.connect(masterGain);
            osc.start(now + idx * 0.12);
            osc.stop(now + idx * 0.12 + 0.12);
          });
          break;
        }

        case 'ERROR_OCCURRED': {
          // Low saw buzz
          const osc = ctx.createOscillator();
          const gain = ctx.createGain();
          osc.type = 'sawtooth';
          osc.frequency.setValueAtTime(160, now);
          osc.frequency.linearRampToValueAtTime(110, now + 0.25);

          gain.gain.setValueAtTime(0.25, now);
          gain.gain.exponentialRampToValueAtTime(0.001, now + 0.28);

          osc.connect(gain);
          gain.connect(masterGain);
          osc.start(now);
          osc.stop(now + 0.3);
          break;
        }

        case 'CLICK_CUE': {
          // Subtle tactile click
          const osc = ctx.createOscillator();
          const gain = ctx.createGain();
          osc.type = 'sine';
          osc.frequency.setValueAtTime(1200, now);
          osc.frequency.exponentialRampToValueAtTime(300, now + 0.03);

          gain.gain.setValueAtTime(0.08, now);
          gain.gain.exponentialRampToValueAtTime(0.001, now + 0.03);

          osc.connect(gain);
          gain.connect(masterGain);
          osc.start(now);
          osc.stop(now + 0.035);
          break;
        }
      }
    } catch {
      // Audio playback fails gracefully without interrupting application functionality
    }
  }
}

export const soundManager = new SoundManager();

