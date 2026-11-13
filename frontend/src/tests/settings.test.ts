import { describe, it, expect, beforeEach, vi } from 'vitest';
import {
  DEFAULT_SETTINGS,
  loadSettings,
  saveSettings,
  UserSettings,
} from '../types/settings';

describe('Settings & Customization Persistence', () => {
  let localStorageMock: Record<string, string> = {};

  beforeEach(() => {
    localStorageMock = {};
    vi.stubGlobal('localStorage', {
      getItem: (key: string) => localStorageMock[key] || null,
      setItem: (key: string, value: string) => {
        localStorageMock[key] = value;
      },
      removeItem: (key: string) => {
        delete localStorageMock[key];
      },
      clear: () => {
        localStorageMock = {};
      },
    });
  });

  it('returns default settings when storage is empty', () => {
    const loaded = loadSettings();
    expect(loaded).toEqual(DEFAULT_SETTINGS);
    expect(loaded.theme).toBe('cyan');
    expect(loaded.panelOpacity).toBe(0.50);
    expect(loaded.soundEnabled).toBe(true);
    expect(loaded.soundVolume).toBe(50);
  });

  it('saves and reloads valid customized settings', () => {
    const custom: UserSettings = {
      ...DEFAULT_SETTINGS,
      theme: 'amber',
      panelOpacity: 0.9,
      soundVolume: 80,
      density: 'compact',
    };

    saveSettings(custom);
    const reloaded = loadSettings();

    expect(reloaded.theme).toBe('amber');
    expect(reloaded.panelOpacity).toBe(0.9);
    expect(reloaded.soundVolume).toBe(80);
    expect(reloaded.density).toBe('compact');
  });

  it('safely recovers to defaults when storage contains corrupted JSON', () => {
    localStorageMock['jarvis_hud_settings_v1'] = 'CORRUPTED_NON_JSON{{{';
    const loaded = loadSettings();
    expect(loaded).toEqual(DEFAULT_SETTINGS);
  });

  it('validates and clamps out-of-bound numerical settings', () => {
    localStorageMock['jarvis_hud_settings_v1'] = JSON.stringify({
      theme: 'invalid_theme',
      panelOpacity: 2.5, // Exceeds 1.0
      soundVolume: -50,  // Sub-zero
    });

    const loaded = loadSettings();
    expect(loaded.theme).toBe(DEFAULT_SETTINGS.theme);
    expect(loaded.panelOpacity).toBe(DEFAULT_SETTINGS.panelOpacity);
    expect(loaded.soundVolume).toBe(DEFAULT_SETTINGS.soundVolume);
  });
});

