import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { DEFAULT_SETTINGS } from '../types/settings';
import { SettingsModal } from '../components/SettingsModal';
import * as api from '../services/api';
import { voicePlayer } from '../services/voiceService';
import { TTSProviderInfo, VoiceProfile } from '../types/contracts';

describe('Voice Library Foundation Suite (Milestone 2.0)', () => {
  const mockProviders: TTSProviderInfo[] = [
    {
      id: 'sapi5',
      name: 'Windows SAPI 5',
      status: 'installed_ready',
      description: 'Windows SAPI engine',
      is_local: true,
      supports_custom_voices: false,
      supports_pitch: false,
      supports_emotions: false,
      voice_count: 2,
    },
    {
      id: 'xtts-v2',
      name: 'Coqui XTTS-v2',
      status: 'not_installed',
      description: 'Coqui XTTS engine',
      is_local: true,
      supports_custom_voices: true,
      supports_pitch: false,
      supports_emotions: true,
      voice_count: 0,
      error_message: 'Coqui TTS package is not installed.',
    },
    {
      id: 'piper',
      name: 'Piper Neural TTS',
      status: 'installed_ready',
      description: 'Piper neural TTS engine',
      is_local: true,
      supports_custom_voices: false,
      supports_pitch: false,
      supports_emotions: false,
      voice_count: 1,
    },
  ];

  const mockProfiles: VoiceProfile[] = [
    {
      id: 'jarvis-default',
      name: 'J.A.R.V.I.S. Standard (David)',
      provider_id: 'sapi5',
      voice_id: 'david',
      language: 'en-US',
      rate: 180,
      pitch: 1.0,
      volume: 100,
      is_favorite: true,
      is_fallback: true,
      is_default: true,
      metadata: {},
    },
    {
      id: 'piper-lessac',
      name: 'Piper Neural (Lessac)',
      provider_id: 'piper',
      voice_id: 'en_US-lessac-medium',
      language: 'en-US',
      rate: 180,
      pitch: 1.0,
      volume: 100,
      is_favorite: false,
      is_fallback: false,
      is_default: false,
      metadata: {},
    },
    {
      id: 'custom-xtts',
      name: 'XTTS Neural Clone: Authorized Voice',
      provider_id: 'xtts-v2',
      voice_id: 'custom-1',
      language: 'en-US',
      rate: 175,
      pitch: 1.0,
      volume: 100,
      is_favorite: false,
      is_fallback: false,
      is_default: false,
      metadata: {},
    },
  ];

  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(api, 'fetchTTSProviders').mockResolvedValue(mockProviders);
    vi.spyOn(api, 'fetchVoiceProfiles').mockResolvedValue(mockProfiles);
    vi.spyOn(api, 'fetchVoicepacks').mockResolvedValue([
      {
        id: 'en_US-lessac-medium',
        name: 'Lessac Medium (en_US)',
        provider_id: 'piper',
        language: 'en-US',
        model_path: 'path/to/model.onnx',
        config_path: 'path/to/config.json',
        sample_rate: 22050,
        num_speakers: 1,
        speakers: ['default'],
        size_bytes: 60000000,
        status: 'installed',
        is_builtin: true,
      },
    ]);
    vi.spyOn(api, 'fetchVoiceList').mockResolvedValue({
      voices: [
        { id: 'david', name: 'Microsoft David Desktop', languages: ['en-US'], is_default: true },
        { id: 'zira', name: 'Microsoft Zira Desktop', languages: ['en-US'], is_default: false },
      ],
      default_voice_id: 'david',
    });
    vi.spyOn(api, 'fetchModelsStorageStatus').mockResolvedValue({
      active_models_dir: 'D:\\Raihan\\JARVIS_MODELS',
      is_external: true,
      total_size_mb: 827.84,
      stt_models_count: 3,
      tts_voicepacks_count: 1,
      rvc_models_count: 6,
      scan_directories: ['D:\\Raihan\\JARVIS_MODELS'],
    });
  });

  it('renders all TTS Engine Status badges with accurate status labels', async () => {
    await act(async () => {
      render(
        <SettingsModal
          isOpen={true}
          settings={DEFAULT_SETTINGS}
          onUpdateSettings={vi.fn()}
          onResetDefaults={vi.fn()}
          onClose={vi.fn()}
        />
      );
    });

    expect(await screen.findByText('TTS Engine Status')).toBeDefined();
    expect(await screen.findByText('Windows SAPI 5:')).toBeDefined();
    expect((await screen.findAllByText('Installed & Ready')).length).toBeGreaterThanOrEqual(1);
    expect(await screen.findByText('Coqui XTTS-v2:')).toBeDefined();
    expect(await screen.findByText('Not Installed')).toBeDefined();
    expect(await screen.findByText('Piper Neural TTS:')).toBeDefined();
  });

  it('populates the voice profiles dropdown and allows switching profiles', async () => {
    const handleUpdateSettings = vi.fn();
    const setActiveSpy = vi.spyOn(api, 'setActiveVoiceProfile').mockResolvedValue(mockProfiles[1]);

    await act(async () => {
      render(
        <SettingsModal
          isOpen={true}
          settings={DEFAULT_SETTINGS}
          onUpdateSettings={handleUpdateSettings}
          onResetDefaults={vi.fn()}
          onClose={vi.fn()}
        />
      );
    });

    const select = screen.getByTestId('voice-profile-select') as HTMLSelectElement;
    expect(select).toBeDefined();
    expect(select.children.length).toBe(3);

    // Switch to Piper profile
    await act(async () => {
      fireEvent.change(select, { target: { value: 'piper-lessac' } });
    });

    expect(handleUpdateSettings).toHaveBeenCalled();
    expect(setActiveSpy).toHaveBeenCalledWith('piper-lessac');
  });

  it('displays fallback routing explanation banner for unavailable engines', async () => {
    await act(async () => {
      render(
        <SettingsModal
          isOpen={true}
          settings={DEFAULT_SETTINGS}
          onUpdateSettings={vi.fn()}
          onResetDefaults={vi.fn()}
          onClose={vi.fn()}
        />
      );
    });

    expect(
      screen.getByText(/If an offline or uninstalled engine profile is selected, synthesis automatically routes/i)
    ).toBeDefined();
  });

  it('triggers voice preview via generateVoicePreview API and plays audio', async () => {
    const previewSpy = vi.spyOn(api, 'generateVoicePreview').mockResolvedValue({
      audio_base64: 'UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQAAAAA=',
      mime_type: 'audio/wav',
      duration_seconds: 0.5,
      voice_used: 'sapi5-david',
      provider_used: 'sapi5',
      fallback_applied: false,
    });
    const playSpy = vi.spyOn(voicePlayer, 'playBase64Wav').mockResolvedValue(undefined);

    await act(async () => {
      render(
        <SettingsModal
          isOpen={true}
          settings={DEFAULT_SETTINGS}
          onUpdateSettings={vi.fn()}
          onResetDefaults={vi.fn()}
          onClose={vi.fn()}
        />
      );
    });

    const testBtn = screen.getByText('▶ Test Voice');
    await act(async () => {
      fireEvent.click(testBtn);
    });

    expect(previewSpy).toHaveBeenCalledWith(
      expect.objectContaining({
        profile_id: 'jarvis-default',
        rate: 180,
        volume: 100,
      })
    );
    expect(playSpy).toHaveBeenCalledWith(
      'UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQAAAAA=',
      expect.objectContaining({ volume: 100 })
    );
  });
});

