/**
 * JARVIS HUD Settings & Customization Type Definitions.
 */

import { DeliveryProfile } from '../services/speechTiming';
import { NarrationSettings, DEFAULT_NARRATION_SETTINGS } from './narration';

export type ThemeAccent = 'cyan' | 'amber' | 'emerald' | 'crimson' | 'violet';

export interface ThemeColors {
  primary: string;
  glow: string;
  dim: string;
  name: string;
}

export const THEME_PALETTES: Record<ThemeAccent, ThemeColors> = {
  cyan: {
    primary: '#00e5ff',
    glow: 'rgba(0, 229, 255, 0.45)',
    dim: 'rgba(0, 229, 255, 0.15)',
    name: 'Mark VII Cyan (Default)',
  },
  amber: {
    primary: '#f59e0b',
    glow: 'rgba(245, 158, 11, 0.45)',
    dim: 'rgba(245, 158, 11, 0.15)',
    name: 'Tactical Amber',
  },
  emerald: {
    primary: '#10b981',
    glow: 'rgba(16, 185, 129, 0.45)',
    dim: 'rgba(16, 185, 129, 0.15)',
    name: 'Hologram Emerald',
  },
  crimson: {
    primary: '#ef4444',
    glow: 'rgba(239, 68, 68, 0.45)',
    dim: 'rgba(239, 68, 68, 0.15)',
    name: 'Stealth Crimson',
  },
  violet: {
    primary: '#a855f7',
    glow: 'rgba(168, 85, 247, 0.45)',
    dim: 'rgba(168, 85, 247, 0.15)',
    name: 'Bifrost Violet',
  },
};

export type AnimationIntensity = 'full' | 'reduced' | 'minimal';
export type InterfaceDensity = 'comfortable' | 'compact';

export type PanelId =
  | 'diagnostics'
  | 'systemMetrics'
  | 'activityLog'
  | 'conversationPreview'
  | 'approvalPreview';

export interface PanelConfig {
  id: PanelId;
  title: string;
  visible: boolean;
  minimized: boolean;
  order: number;
}

export interface VoiceSettings {
  voiceOutputEnabled: boolean;
  speechInputEnabled: boolean;
  selectedVoiceId: string;
  activeProfileId?: string;
  speakingRate: number; // 100 to 250 wpm
  volume: number; // 0 to 100
  pitch?: number; // 0.5 to 2.0 (1.0 = default)
  deliveryProfile?: DeliveryProfile; // 'relaxed' | 'conversational' | 'formal'
  autoPlayback: boolean;
  sttModelSize?: string; // 'base.en' | 'tiny.en'
  narration?: NarrationSettings;
}

export interface KeybindSettings {
  toggleMic: string;
  toggleHud: string;
  inspectScreen: string;
  stopSpeaking: string;
}

export const DEFAULT_KEYBINDS: KeybindSettings = {
  toggleMic: 'Ctrl+Space',
  toggleHud: 'Alt+Space',
  inspectScreen: 'Ctrl+Shift+S',
  stopSpeaking: 'Escape',
};

export interface UserSettings {
  version: number;
  theme: ThemeAccent;
  animationIntensity: AnimationIntensity;
  reducedMotion: boolean;
  density: InterfaceDensity;
  panelOpacity: number; // 0.2 to 1.0
  soundEnabled: boolean;
  soundVolume: number; // 0 to 100
  voice: VoiceSettings;
  keybinds: KeybindSettings;
  panels: Record<PanelId, PanelConfig>;
}

export const DEFAULT_VOICE_SETTINGS: VoiceSettings = {
  voiceOutputEnabled: true,
  speechInputEnabled: true,
  selectedVoiceId: '',
  activeProfileId: 'jarvis-default',
  speakingRate: 180,
  volume: 100,
  pitch: 1.0,
  deliveryProfile: 'relaxed',
  autoPlayback: true,
  sttModelSize: 'base.en',
  narration: DEFAULT_NARRATION_SETTINGS,
};

export const DEFAULT_SETTINGS: UserSettings = {
  version: 1,
  theme: 'cyan',
  animationIntensity: 'full',
  reducedMotion: false,
  density: 'comfortable',
  panelOpacity: 0.50,
  soundEnabled: true,
  soundVolume: 50,
  voice: DEFAULT_VOICE_SETTINGS,
  keybinds: DEFAULT_KEYBINDS,
  panels: {
    diagnostics: {
      id: 'diagnostics',
      title: 'Subsystem Integrity',
      visible: true,
      minimized: false,
      order: 0,
    },
    systemMetrics: {
      id: 'systemMetrics',
      title: 'Host Telemetry',
      visible: true,
      minimized: false,
      order: 1,
    },
    activityLog: {
      id: 'activityLog',
      title: 'Activity & Audit Log',
      visible: true,
      minimized: false,
      order: 2,
    },
    conversationPreview: {
      id: 'conversationPreview',
      title: 'Live Conversation Stream',
      visible: true,
      minimized: false,
      order: 3,
    },
    approvalPreview: {
      id: 'approvalPreview',
      title: 'Pending Authorization',
      visible: true,
      minimized: false,
      order: 4,
    },
  },
};

const SETTINGS_STORAGE_KEY = 'jarvis_hud_settings_v1';

/**
 * Loads and validates settings from localStorage with fallback to defaults.
 */
export function loadSettings(): UserSettings {
  if (typeof localStorage === 'undefined') {
    return DEFAULT_SETTINGS;
  }

  try {
    const raw = localStorage.getItem(SETTINGS_STORAGE_KEY);
    if (!raw) return DEFAULT_SETTINGS;

    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== 'object') return DEFAULT_SETTINGS;

    // Validate theme
    const theme: ThemeAccent = THEME_PALETTES[parsed.theme as ThemeAccent]
      ? (parsed.theme as ThemeAccent)
      : DEFAULT_SETTINGS.theme;

    // Validate animation intensity
    const animationIntensity: AnimationIntensity = ['full', 'reduced', 'minimal'].includes(
      parsed.animationIntensity
    )
      ? parsed.animationIntensity
      : DEFAULT_SETTINGS.animationIntensity;

    // Validate density
    const density: InterfaceDensity = ['comfortable', 'compact'].includes(parsed.density)
      ? parsed.density
      : DEFAULT_SETTINGS.density;

    // Validate opacity
    const panelOpacity =
      typeof parsed.panelOpacity === 'number' &&
      parsed.panelOpacity >= 0.5 &&
      parsed.panelOpacity <= 1.0
        ? parsed.panelOpacity
        : DEFAULT_SETTINGS.panelOpacity;

    // Validate sound settings
    const soundEnabled = typeof parsed.soundEnabled === 'boolean' ? parsed.soundEnabled : true;
    const soundVolume =
      typeof parsed.soundVolume === 'number' && parsed.soundVolume >= 0 && parsed.soundVolume <= 100
        ? parsed.soundVolume
        : 50;

    // Validate voice settings
    const rawVoice = parsed.voice && typeof parsed.voice === 'object' ? parsed.voice : {};
    const voice: VoiceSettings = {
      voiceOutputEnabled:
        typeof rawVoice.voiceOutputEnabled === 'boolean'
          ? rawVoice.voiceOutputEnabled
          : DEFAULT_VOICE_SETTINGS.voiceOutputEnabled,
      speechInputEnabled:
        typeof rawVoice.speechInputEnabled === 'boolean'
          ? rawVoice.speechInputEnabled
          : DEFAULT_VOICE_SETTINGS.speechInputEnabled,
      selectedVoiceId:
        typeof rawVoice.selectedVoiceId === 'string'
          ? rawVoice.selectedVoiceId
          : DEFAULT_VOICE_SETTINGS.selectedVoiceId,
      activeProfileId:
        typeof rawVoice.activeProfileId === 'string'
          ? rawVoice.activeProfileId
          : DEFAULT_VOICE_SETTINGS.activeProfileId,
      speakingRate:
        typeof rawVoice.speakingRate === 'number' &&
        rawVoice.speakingRate >= 80 &&
        rawVoice.speakingRate <= 300
          ? rawVoice.speakingRate
          : DEFAULT_VOICE_SETTINGS.speakingRate,
      volume:
        typeof rawVoice.volume === 'number' &&
        rawVoice.volume >= 0 &&
        rawVoice.volume <= 100
          ? rawVoice.volume
          : DEFAULT_VOICE_SETTINGS.volume,
      pitch:
        typeof rawVoice.pitch === 'number' &&
        rawVoice.pitch >= 0.5 &&
        rawVoice.pitch <= 2.0
          ? rawVoice.pitch
          : DEFAULT_VOICE_SETTINGS.pitch,
      autoPlayback:
        typeof rawVoice.autoPlayback === 'boolean'
          ? rawVoice.autoPlayback
          : DEFAULT_VOICE_SETTINGS.autoPlayback,
      sttModelSize:
        rawVoice.sttModelSize === 'tiny.en' || rawVoice.sttModelSize === 'base.en'
          ? rawVoice.sttModelSize
          : DEFAULT_VOICE_SETTINGS.sttModelSize,
      narration: {
        ...DEFAULT_NARRATION_SETTINGS,
        ...(rawVoice.narration && typeof rawVoice.narration === 'object' ? rawVoice.narration : {}),
      },
    };

    // Validate keybinds
    const rawKeybinds = parsed.keybinds && typeof parsed.keybinds === 'object' ? parsed.keybinds : {};
    const keybinds: KeybindSettings = {
      toggleMic:
        typeof rawKeybinds.toggleMic === 'string' && rawKeybinds.toggleMic.trim()
          ? rawKeybinds.toggleMic.trim()
          : DEFAULT_KEYBINDS.toggleMic,
      toggleHud:
        typeof rawKeybinds.toggleHud === 'string' && rawKeybinds.toggleHud.trim()
          ? rawKeybinds.toggleHud.trim()
          : DEFAULT_KEYBINDS.toggleHud,
      inspectScreen:
        typeof rawKeybinds.inspectScreen === 'string' && rawKeybinds.inspectScreen.trim()
          ? rawKeybinds.inspectScreen.trim()
          : DEFAULT_KEYBINDS.inspectScreen,
      stopSpeaking:
        typeof rawKeybinds.stopSpeaking === 'string' && rawKeybinds.stopSpeaking.trim()
          ? rawKeybinds.stopSpeaking.trim()
          : DEFAULT_KEYBINDS.stopSpeaking,
    };

    // Merge panels safely
    const panels: Record<PanelId, PanelConfig> = { ...DEFAULT_SETTINGS.panels };
    if (parsed.panels && typeof parsed.panels === 'object') {
      for (const id of Object.keys(DEFAULT_SETTINGS.panels) as PanelId[]) {
        if (parsed.panels[id]) {
          panels[id] = {
            ...DEFAULT_SETTINGS.panels[id],
            visible: typeof parsed.panels[id].visible === 'boolean' ? parsed.panels[id].visible : true,
            minimized:
              typeof parsed.panels[id].minimized === 'boolean'
                ? parsed.panels[id].minimized
                : false,
            order:
              typeof parsed.panels[id].order === 'number'
                ? parsed.panels[id].order
                : DEFAULT_SETTINGS.panels[id].order,
          };
        }
      }
    }

    return {
      version: 1,
      theme,
      animationIntensity,
      reducedMotion: Boolean(parsed.reducedMotion),
      density,
      panelOpacity,
      soundEnabled,
      soundVolume,
      voice,
      keybinds,
      panels,
    };
  } catch (e) {
    console.warn('Failed to parse saved JARVIS settings, resetting to defaults:', e);
    return DEFAULT_SETTINGS;
  }
}

/**
 * Saves validated settings to localStorage.
 */
export function saveSettings(settings: UserSettings): void {
  if (typeof localStorage === 'undefined') return;
  try {
    localStorage.setItem(SETTINGS_STORAGE_KEY, JSON.stringify(settings));
  } catch (e) {
    console.warn('Failed to save JARVIS settings to localStorage:', e);
  }
}
