import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { DEFAULT_SETTINGS, loadSettings, saveSettings } from '../types/settings';
import { ArcReactor } from '../components/ArcReactor';
import { SettingsModal } from '../components/SettingsModal';
import * as api from '../services/api';

describe('Voice Stabilization & Custom Keybindings Suite', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });

  describe('Keybindings & Voice Settings Storage Contract', () => {
    it('initializes default keybindings and base.en STT model correctly', () => {
      const settings = loadSettings();
      expect(settings.keybinds).toBeDefined();
      expect(settings.keybinds.toggleMic).toBe('Ctrl+Space');
      expect(settings.keybinds.toggleHud).toBe('Alt+Space');
      expect(settings.keybinds.inspectScreen).toBe('Ctrl+Shift+S');
      expect(settings.keybinds.stopSpeaking).toBe('Escape');
      expect(settings.voice.sttModelSize).toBe('base.en');
      expect(settings.voice.speakingRate).toBe(180);
      expect(settings.voice.volume).toBe(100);
    });

    it('persists and restores custom keybindings from localStorage', () => {
      const customSettings = {
        ...DEFAULT_SETTINGS,
        keybinds: {
          toggleMic: 'Alt+M',
          toggleHud: 'F4',
          inspectScreen: 'Ctrl+I',
          stopSpeaking: 'Escape',
        },
        voice: {
          ...DEFAULT_SETTINGS.voice,
          sttModelSize: 'tiny.en',
        },
      };

      saveSettings(customSettings);
      const loaded = loadSettings();

      expect(loaded.keybinds.toggleMic).toBe('Alt+M');
      expect(loaded.keybinds.toggleHud).toBe('F4');
      expect(loaded.keybinds.inspectScreen).toBe('Ctrl+I');
      expect(loaded.voice.sttModelSize).toBe('tiny.en');
    });
  });

  describe('ArcReactor Error / FAULT Clearance', () => {
    it('triggers onClearError when clicked in ERROR state', () => {
      const handleClearError = vi.fn();
      const handleActivate = vi.fn();

      render(
        <ArcReactor
          assistantState="ERROR"
          latencyMs={45}
          onActivate={handleActivate}
          onClearError={handleClearError}
        />
      );

      const orb = screen.getByText('ERROR');
      fireEvent.click(orb);

      expect(handleClearError).toHaveBeenCalledTimes(1);
      expect(handleActivate).not.toHaveBeenCalled();
    });

    it('calls onStopSpeaking when clicked in SPEAKING state', () => {
      const handleStopSpeaking = vi.fn();
      const handleActivate = vi.fn();

      render(
        <ArcReactor
          assistantState="SPEAKING"
          latencyMs={30}
          onActivate={handleActivate}
          onStopSpeaking={handleStopSpeaking}
        />
      );

      const orb = screen.getByText('SPEAKING');
      fireEvent.click(orb);

      expect(handleStopSpeaking).toHaveBeenCalledTimes(1);
      expect(handleActivate).not.toHaveBeenCalled();
    });
  });

  describe('SettingsModal Keybindings & STT Model UI', () => {
    it('renders Custom Keybindings & Shortcuts panel and STT Model selector', async () => {
      vi.spyOn(api, 'fetchVoiceList').mockResolvedValue({
        voices: [{ id: 'v1', name: 'Microsoft David', languages: ['en-US'], is_default: true }],
        default_voice_id: 'v1',
      });

      const handleUpdateSettings = vi.fn();
      const handleResetDefaults = vi.fn();
      const handleClose = vi.fn();

      await act(async () => {
        render(
          <SettingsModal
            isOpen={true}
            settings={DEFAULT_SETTINGS}
            onUpdateSettings={handleUpdateSettings}
            onResetDefaults={handleResetDefaults}
            onClose={handleClose}
          />
        );
      });

      // Verify custom keybindings panel headers & buttons
      expect(screen.getByText('Custom Keybindings & Global Shortcuts')).toBeDefined();
      expect(screen.getByText('Push-to-Talk / Mic Toggle')).toBeDefined();
      expect(screen.getByText('Summon / Dismiss HUD')).toBeDefined();
      expect(screen.getByText('Screen Perception & OCR')).toBeDefined();
      expect(screen.getByText('Stop Speaking / Cancel')).toBeDefined();
      expect(screen.getByText('↺ Reset Shortcuts')).toBeDefined();

      // Verify STT Model dropdown is present
      expect(screen.getByText(/Speech-to-Text Model \(Faster-Whisper\)/i)).toBeDefined();
    });

    it('allows changing STT Whisper model size and notifies backend API', async () => {
      vi.spyOn(api, 'fetchVoiceList').mockResolvedValue({ voices: [], default_voice_id: '' });
      const setSTTModelSpy = vi.spyOn(api, 'setSTTModel').mockResolvedValue({
        status: 'ok',
        model_size: 'tiny.en',
      });

      let currentSettings = { ...DEFAULT_SETTINGS };
      const handleUpdate = vi.fn((updater) => {
        currentSettings = updater(currentSettings);
      });

      await act(async () => {
        render(
          <SettingsModal
            isOpen={true}
            settings={currentSettings}
            onUpdateSettings={handleUpdate}
            onResetDefaults={vi.fn()}
            onClose={vi.fn()}
          />
        );
      });

      // Find the select element containing the models
      const selectElements = screen.getAllByRole('combobox');
      // The STT model select will have 'base.en' value
      const sttSelect = selectElements.find((el) => (el as HTMLSelectElement).value === 'base.en');
      expect(sttSelect).toBeDefined();

      await act(async () => {
        fireEvent.change(sttSelect!, { target: { value: 'tiny.en' } });
      });

      expect(handleUpdate).toHaveBeenCalled();
      expect(setSTTModelSpy).toHaveBeenCalledWith('tiny.en');
    });

    it('resets shortcuts to defaults when Reset Shortcuts button is clicked', async () => {
      vi.spyOn(api, 'fetchVoiceList').mockResolvedValue({ voices: [], default_voice_id: '' });

      const customSettings = {
        ...DEFAULT_SETTINGS,
        keybinds: {
          toggleMic: 'Alt+M',
          toggleHud: 'F1',
          inspectScreen: 'Ctrl+Shift+P',
          stopSpeaking: 'Escape',
        },
      };

      const handleUpdate = vi.fn();

      await act(async () => {
        render(
          <SettingsModal
            isOpen={true}
            settings={customSettings}
            onUpdateSettings={handleUpdate}
            onResetDefaults={vi.fn()}
            onClose={vi.fn()}
          />
        );
      });

      const resetBtn = screen.getByText('↺ Reset Shortcuts');
      fireEvent.click(resetBtn);

      expect(handleUpdate).toHaveBeenCalled();
    });
  });
});
