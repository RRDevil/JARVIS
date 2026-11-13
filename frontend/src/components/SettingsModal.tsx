import React, { useEffect, useState } from 'react';
import {
  UserSettings,
  THEME_PALETTES,
  ThemeAccent,
  AnimationIntensity,
  InterfaceDensity,
  PanelId,
  KeybindSettings,
  DEFAULT_KEYBINDS,
} from '../types/settings';
import { soundManager } from '../services/soundManager';
import {
  fetchVoiceList,
  setSTTModel,
  fetchTTSProviders,
  fetchVoiceProfiles,
  setActiveVoiceProfile,
  generateVoicePreview,
  fetchVoicepacks,
  importVoicepack,
  deleteVoicepack,
  fetchModelsStorageStatus,
  configureModelsPath,
  importModelFromPath,
} from '../services/api';
import { VoiceInfo, VoiceProfile, TTSProviderInfo, VoicepackInfo, ModelsStorageStatus } from '../types/contracts';
import { voicePlayer } from '../services/voiceService';
import { DeliveryProfile, DELIVERY_PROFILES } from '../services/speechTiming';

interface KeybindActionMeta {
  key: keyof KeybindSettings;
  label: string;
  description: string;
}

const KEYBIND_ACTIONS: KeybindActionMeta[] = [
  {
    key: 'toggleMic',
    label: 'Push-to-Talk / Mic Toggle',
    description: 'Toggle microphone recording to speak a command to JARVIS',
  },
  {
    key: 'toggleHud',
    label: 'Summon / Dismiss HUD',
    description: 'Toggle holographic dashboard from compact orb mode',
  },
  {
    key: 'inspectScreen',
    label: 'Screen Perception & OCR',
    description: 'Open screen capture, OCR, and multimodal vision window',
  },
  {
    key: 'stopSpeaking',
    label: 'Stop Speaking / Cancel',
    description: 'Instantly mute and halt current voice response playback',
  },
];

interface SettingsModalProps {
  isOpen: boolean;
  settings: UserSettings;
  onUpdateSettings: (updater: (prev: UserSettings) => UserSettings) => void;
  onResetDefaults: () => void;
  onClose: () => void;
}

export const SettingsModal: React.FC<SettingsModalProps> = ({
  isOpen,
  settings,
  onUpdateSettings,
  onResetDefaults,
  onClose,
}) => {
  const [availableVoices, setAvailableVoices] = useState<VoiceInfo[]>([]);
  const [voiceProfiles, setVoiceProfiles] = useState<VoiceProfile[]>([]);
  const [ttsProviders, setTtsProviders] = useState<TTSProviderInfo[]>([]);
  const [voicepacks, setVoicepacks] = useState<VoicepackInfo[]>([]);
  const [isImportingVoicepack, setIsImportingVoicepack] = useState(false);
  const [voicepackStatusMsg, setVoicepackStatusMsg] = useState<string | null>(null);
  const [modelsStatus, setModelsStatus] = useState<ModelsStorageStatus | null>(null);
  const [externalPathInput, setExternalPathInput] = useState<string>('');
  const [isConfiguringPath, setIsConfiguringPath] = useState(false);
  const [importPathInput, setImportPathInput] = useState<string>('');
  const [importPathNameInput, setImportPathNameInput] = useState<string>('');
  const [isImportingPath, setIsImportingPath] = useState(false);
  const [modelsMsg, setModelsMsg] = useState<string | null>(null);
  const [isTestingVoice, setIsTestingVoice] = useState(false);
  const [recordingKeybindAction, setRecordingKeybindAction] = useState<keyof KeybindSettings | null>(null);
  const [keybindConflict, setKeybindConflict] = useState<string | null>(null);

  // Interactive Keybind Recording Listener
  useEffect(() => {
    if (!recordingKeybindAction) return;

    const handleKeyRecord = (e: KeyboardEvent) => {
      e.preventDefault();
      e.stopPropagation();

      // Ignore bare modifier key presses
      if (['Control', 'Shift', 'Alt', 'Meta'].includes(e.key)) {
        return;
      }

      // Format human-readable shortcut string
      const parts: string[] = [];
      if (e.ctrlKey) parts.push('Ctrl');
      if (e.altKey) parts.push('Alt');
      if (e.shiftKey) parts.push('Shift');
      if (e.metaKey) parts.push('Win');

      let mainKey = e.key;
      if (mainKey === ' ') mainKey = 'Space';
      else if (mainKey.length === 1) mainKey = mainKey.toUpperCase();
      else if (e.code === 'ScrollLock') mainKey = 'ScrollLock';
      else if (e.code === 'Pause') mainKey = 'Pause';

      parts.push(mainKey);
      const combo = parts.join('+');

      // Check for conflicts across other actions
      const currentBinds = settings.keybinds || DEFAULT_KEYBINDS;
      const conflictKey = (Object.keys(currentBinds) as (keyof KeybindSettings)[]).find(
        (k) => k !== recordingKeybindAction && currentBinds[k]?.toLowerCase() === combo.toLowerCase()
      );

      if (conflictKey) {
        setKeybindConflict(`'${combo}' is already assigned to ${conflictKey}`);
        return;
      }

      setKeybindConflict(null);
      soundManager.play('CLICK_CUE');
      const updatedKeybinds: KeybindSettings = {
        ...currentBinds,
        [recordingKeybindAction]: combo,
      };

      onUpdateSettings((prev) => ({
        ...prev,
        keybinds: updatedKeybinds,
      }));

      // Notify native pywebview desktop bridge if running in desktop app
      if ((window as any).pywebview?.api?.update_hotkeys) {
        (window as any).pywebview.api.update_hotkeys(updatedKeybinds);
      }

      setRecordingKeybindAction(null);
    };

    window.addEventListener('keydown', handleKeyRecord, true);
    return () => window.removeEventListener('keydown', handleKeyRecord, true);
  }, [recordingKeybindAction, settings.keybinds, onUpdateSettings]);

  useEffect(() => {
    let mounted = true;
    if (isOpen) {
      Promise.allSettled([
        fetchVoiceList(),
        fetchVoiceProfiles(),
        fetchTTSProviders(),
        fetchVoicepacks(),
        fetchModelsStorageStatus(),
      ]).then(([voicesRes, profilesRes, providersRes, voicepacksRes, modelsRes]) => {
        if (!mounted) return;
        if (voicesRes.status === 'fulfilled' && voicesRes.value?.voices) {
          setAvailableVoices(voicesRes.value.voices);
          if (!settings.voice.selectedVoiceId && voicesRes.value.default_voice_id) {
            onUpdateSettings((prev) => ({
              ...prev,
              voice: { ...prev.voice, selectedVoiceId: voicesRes.value.default_voice_id },
            }));
          }
        }
        if (profilesRes.status === 'fulfilled' && Array.isArray(profilesRes.value)) {
          setVoiceProfiles(profilesRes.value);
        }
        if (providersRes.status === 'fulfilled' && Array.isArray(providersRes.value)) {
          setTtsProviders(providersRes.value);
        }
        if (voicepacksRes.status === 'fulfilled' && Array.isArray(voicepacksRes.value)) {
          setVoicepacks(voicepacksRes.value);
        }
        if (modelsRes.status === 'fulfilled' && modelsRes.value) {
          setModelsStatus(modelsRes.value);
          setExternalPathInput(modelsRes.value.active_models_dir);
        }
      }).catch((e) => console.warn('Could not load voice library settings:', e));
    }
    return () => {
      mounted = false;
    };
  }, [isOpen, settings.voice.selectedVoiceId, onUpdateSettings]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
      }
    };
    if (isOpen) {
      window.addEventListener('keydown', handleKeyDown);
    }
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const handleVoiceOutputToggle = (e: React.ChangeEvent<HTMLInputElement>) => {
    const enabled = e.target.checked;
    soundManager.play('CLICK_CUE');
    onUpdateSettings((prev) => ({
      ...prev,
      voice: { ...prev.voice, voiceOutputEnabled: enabled },
    }));
  };

  const handleVoiceInputToggle = (e: React.ChangeEvent<HTMLInputElement>) => {
    const enabled = e.target.checked;
    soundManager.play('CLICK_CUE');
    onUpdateSettings((prev) => ({
      ...prev,
      voice: { ...prev.voice, speechInputEnabled: enabled },
    }));
  };

  const handleAutoPlaybackToggle = (e: React.ChangeEvent<HTMLInputElement>) => {
    const enabled = e.target.checked;
    soundManager.play('CLICK_CUE');
    onUpdateSettings((prev) => ({
      ...prev,
      voice: { ...prev.voice, autoPlayback: enabled },
    }));
  };

  const handleVoiceChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const voiceId = e.target.value;
    soundManager.play('CLICK_CUE');
    onUpdateSettings((prev) => ({
      ...prev,
      voice: { ...prev.voice, selectedVoiceId: voiceId },
    }));
  };

  const handleSpeakingRateChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const rate = parseInt(e.target.value, 10);
    onUpdateSettings((prev) => ({
      ...prev,
      voice: { ...prev.voice, speakingRate: rate },
    }));
  };

  const handleVoiceVolumeChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const vol = parseInt(e.target.value, 10);
    onUpdateSettings((prev) => ({
      ...prev,
      voice: { ...prev.voice, volume: vol },
    }));
  };

  const handlePitchChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const pitch = parseFloat(e.target.value);
    onUpdateSettings((prev) => ({
      ...prev,
      voice: { ...prev.voice, pitch },
    }));
  };

  const handleDeliveryProfileChange = (profile: DeliveryProfile) => {
    soundManager.play('CLICK_CUE');
    onUpdateSettings((prev) => ({
      ...prev,
      voice: { ...prev.voice, deliveryProfile: profile },
    }));
  };

  const refreshVoiceLibrary = async () => {
    try {
      const [packs, profs, voices, providers] = await Promise.all([
        fetchVoicepacks(),
        fetchVoiceProfiles(),
        fetchVoiceList(),
        fetchTTSProviders(),
      ]);
      setVoicepacks(packs);
      setVoiceProfiles(profs);
      setAvailableVoices(voices.voices);
      setTtsProviders(providers);
    } catch (err) {
      console.warn('Failed to refresh voice library:', err);
    }
  };

  const handleConfigureModelsPath = async () => {
    if (!externalPathInput.trim()) return;
    setIsConfiguringPath(true);
    setModelsMsg('Updating models directory...');
    soundManager.play('CLICK_CUE');
    try {
      const res = await configureModelsPath(externalPathInput.trim());
      setModelsStatus(res);
      setModelsMsg(`Models directory updated: ${res.active_models_dir}`);
      await refreshVoiceLibrary();
    } catch (err: any) {
      setModelsMsg(`Failed: ${err.message || err}`);
    } finally {
      setIsConfiguringPath(false);
      setTimeout(() => setModelsMsg(null), 4000);
    }
  };

  const handleImportFromPath = async () => {
    if (!importPathInput.trim()) return;
    setIsImportingPath(true);
    setModelsMsg('Importing model asset from disk...');
    soundManager.play('CLICK_CUE');
    try {
      const res = await importModelFromPath(importPathInput.trim(), importPathNameInput.trim() || undefined);
      if (res.success) {
        setModelsMsg(`Successfully imported: ${res.voicepack?.name || 'Model'}`);
        setImportPathInput('');
        setImportPathNameInput('');
        await refreshVoiceLibrary();
        const status = await fetchModelsStorageStatus();
        setModelsStatus(status);
      } else {
        setModelsMsg(`Import failed: ${res.message}`);
      }
    } catch (err: any) {
      setModelsMsg(`Import failed: ${err.message || err}`);
    } finally {
      setIsImportingPath(false);
      setTimeout(() => setModelsMsg(null), 4000);
    }
  };

  const handleVoicepackUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setIsImportingVoicepack(true);
    setVoicepackStatusMsg('Importing and validating voicepack...');
    soundManager.play('CLICK_CUE');
    try {
      const res = await importVoicepack(file);
      if (res.success) {
        setVoicepackStatusMsg(`Installed voicepack: ${res.voicepack?.name || ''}`);
        await refreshVoiceLibrary();
      } else {
        setVoicepackStatusMsg(`Error: ${res.message}`);
      }
    } catch (err: any) {
      setVoicepackStatusMsg(`Import failed: ${err.message || err}`);
    } finally {
      setIsImportingVoicepack(false);
      e.target.value = '';
      setTimeout(() => setVoicepackStatusMsg(null), 4000);
    }
  };

  const handleDeleteVoicepack = async (voicepackId: string) => {
    soundManager.play('CLICK_CUE');
    try {
      await deleteVoicepack(voicepackId);
      await refreshVoiceLibrary();
    } catch (err: any) {
      console.warn('Failed to delete voicepack:', err);
    }
  };

  const handleProfileChange = async (e: React.ChangeEvent<HTMLSelectElement>) => {
    const profileId = e.target.value;
    soundManager.play('CLICK_CUE');
    const selectedProfile = voiceProfiles.find((p) => p.id === profileId);
    onUpdateSettings((prev) => ({
      ...prev,
      voice: {
        ...prev.voice,
        activeProfileId: profileId,
        ...(selectedProfile
          ? {
              selectedVoiceId: selectedProfile.voice_id || prev.voice.selectedVoiceId,
              speakingRate: selectedProfile.rate ?? prev.voice.speakingRate,
              volume: selectedProfile.volume ?? prev.voice.volume,
            }
          : {}),
      },
    }));
    try {
      await setActiveVoiceProfile(profileId);
    } catch (err) {
      console.warn('Failed to switch active voice profile on backend:', err);
    }
  };

  const handleTestVoice = async () => {
    if (isTestingVoice) {
      voicePlayer.stop();
      setIsTestingVoice(false);
      return;
    }
    setIsTestingVoice(true);
    soundManager.play('CLICK_CUE');
    try {
      const previewRes = await generateVoicePreview({
        profile_id: settings.voice.activeProfileId,
        voice_id: settings.voice.selectedVoiceId,
        rate: settings.voice.speakingRate,
        volume: settings.voice.volume,
        pitch: settings.voice.pitch || 1.0,
      });
      if (previewRes.audio_base64) {
        await voicePlayer.playBase64Wav(previewRes.audio_base64, {
          volume: settings.voice.volume,
          onEnded: () => setIsTestingVoice(false),
          onError: () => setIsTestingVoice(false),
        });
      } else {
        setIsTestingVoice(false);
      }
    } catch (err) {
      console.warn('Preview synthesis error, falling back to client speakText:', err);
      await voicePlayer.speakText(
        'Sir, vocal synthesis diagnostics are operating normally.',
        settings.voice,
        {
          onEnded: () => setIsTestingVoice(false),
          onError: () => setIsTestingVoice(false),
        }
      );
    }
  };

  const handleSTTModelChange = async (e: React.ChangeEvent<HTMLSelectElement>) => {
    const modelSize = e.target.value;
    soundManager.play('CLICK_CUE');
    onUpdateSettings((prev) => ({
      ...prev,
      voice: { ...prev.voice, sttModelSize: modelSize },
    }));
    try {
      await setSTTModel(modelSize);
    } catch (err) {
      console.warn('Failed to switch STT model on backend:', err);
    }
  };

  const handleStartRecordingKeybind = (key: keyof KeybindSettings) => {
    soundManager.play('CLICK_CUE');
    if (recordingKeybindAction === key) {
      setRecordingKeybindAction(null);
      setKeybindConflict(null);
    } else {
      setRecordingKeybindAction(key);
      setKeybindConflict(null);
    }
  };

  const handleResetKeybinds = () => {
    soundManager.play('CLICK_CUE');
    setKeybindConflict(null);
    setRecordingKeybindAction(null);
    onUpdateSettings((prev) => ({
      ...prev,
      keybinds: { ...DEFAULT_KEYBINDS },
    }));
    if ((window as any).pywebview?.api?.update_hotkeys) {
      (window as any).pywebview.api.update_hotkeys(DEFAULT_KEYBINDS);
    }
  };

  const handleThemeChange = (accent: ThemeAccent) => {
    soundManager.play('CLICK_CUE');
    onUpdateSettings((prev) => ({ ...prev, theme: accent }));
  };

  const handleAnimationChange = (intensity: AnimationIntensity) => {
    soundManager.play('CLICK_CUE');
    onUpdateSettings((prev) => ({ ...prev, animationIntensity: intensity }));
  };

  const handleDensityChange = (density: InterfaceDensity) => {
    soundManager.play('CLICK_CUE');
    onUpdateSettings((prev) => ({ ...prev, density }));
  };

  const handleOpacityChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const opacity = parseFloat(e.target.value);
    onUpdateSettings((prev) => ({ ...prev, panelOpacity: opacity }));
  };

  const handleSoundToggle = (e: React.ChangeEvent<HTMLInputElement>) => {
    const enabled = e.target.checked;
    soundManager.play('CLICK_CUE');
    soundManager.setEnabled(enabled);
    onUpdateSettings((prev) => ({ ...prev, soundEnabled: enabled }));
  };

  const handleVolumeChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const vol = parseInt(e.target.value, 10);
    soundManager.setVolume(vol);
    onUpdateSettings((prev) => ({ ...prev, soundVolume: vol }));
  };

  const handlePanelVisibility = (id: PanelId, visible: boolean) => {
    soundManager.play('CLICK_CUE');
    onUpdateSettings((prev) => ({
      ...prev,
      panels: {
        ...prev.panels,
        [id]: { ...prev.panels[id], visible },
      },
    }));
  };

  return (
    <div
      className="modal-overlay"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-labelledby="settings-title"
    >
      <div className="modal-content" onClick={(e) => e.stopPropagation()}>
        <header className="modal-header">
          <h2 id="settings-title" className="panel-title-text" style={{ fontSize: '1rem' }}>
            System Configuration & Visual Parameters
          </h2>
          <button className="panel-icon-btn" onClick={onClose} aria-label="Close settings">
            ✕
          </button>
        </header>

        <div className="modal-body">
          {/* Accent Palette */}
          <div className="setting-group">
            <label className="setting-label">HUD Accent Illumination</label>
            <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
              {(Object.keys(THEME_PALETTES) as ThemeAccent[]).map((key) => {
                const pal = THEME_PALETTES[key];
                const isSelected = settings.theme === key;
                return (
                  <button
                    key={key}
                    onClick={() => handleThemeChange(key)}
                    style={{
                      background: isSelected ? pal.dim : 'rgba(0,0,0,0.4)',
                      border: `1px solid ${isSelected ? pal.primary : 'rgba(255,255,255,0.1)'}`,
                      color: isSelected ? '#fff' : pal.primary,
                      padding: '0.4rem 0.75rem',
                      borderRadius: '3px',
                      fontFamily: 'var(--hud-font-mono)',
                      fontSize: '0.75rem',
                      cursor: 'pointer',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '0.4rem',
                    }}
                  >
                    <span
                      style={{
                        width: '10px',
                        height: '10px',
                        borderRadius: '50%',
                        background: pal.primary,
                        boxShadow: `0 0 6px ${pal.primary}`,
                      }}
                    />
                    {pal.name}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Interface Density */}
          <div className="setting-group">
            <label className="setting-label">Interface Layout Density</label>
            <div style={{ display: 'flex', gap: '0.5rem' }}>
              {(['comfortable', 'compact'] as InterfaceDensity[]).map((mode) => (
                <button
                  key={mode}
                  className={`sim-btn ${settings.density === mode ? 'active' : ''}`}
                  onClick={() => handleDensityChange(mode)}
                  style={{ textTransform: 'uppercase', padding: '0.35rem 0.8rem' }}
                >
                  {mode}
                </button>
              ))}
            </div>
          </div>

          {/* Animation & Motion */}
          <div className="setting-group">
            <label className="setting-label">Holographic Animation Dynamics</label>
            <div style={{ display: 'flex', gap: '0.5rem' }}>
              {(['full', 'reduced', 'minimal'] as AnimationIntensity[]).map((intensity) => (
                <button
                  key={intensity}
                  className={`sim-btn ${settings.animationIntensity === intensity ? 'active' : ''}`}
                  onClick={() => handleAnimationChange(intensity)}
                  style={{ textTransform: 'uppercase', padding: '0.35rem 0.8rem' }}
                >
                  {intensity}
                </button>
              ))}
            </div>
          </div>

          {/* Panel Opacity Slider */}
          <div className="setting-group">
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <label className="setting-label">Panel Acrylic Opacity</label>
              <span style={{ fontFamily: 'var(--hud-font-mono)', fontSize: '0.8rem', color: 'var(--hud-primary)' }}>
                {Math.round(settings.panelOpacity * 100)}%
              </span>
            </div>
            <input
              type="range"
              min="0.2"
              max="1.0"
              step="0.05"
              value={settings.panelOpacity}
              onChange={handleOpacityChange}
              style={{ width: '100%', accentColor: 'var(--hud-primary)' }}
            />
          </div>

          {/* Sound Cues */}
          <div className="setting-group">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <label className="setting-label">Synthesized Audio Cues</label>
              <label style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', cursor: 'pointer', fontSize: '0.8rem' }}>
                <input
                  type="checkbox"
                  checked={settings.soundEnabled}
                  onChange={handleSoundToggle}
                  style={{ accentColor: 'var(--hud-primary)' }}
                />
                <span>Enable Sound FX</span>
              </label>
            </div>

            {settings.soundEnabled && (
              <div style={{ marginTop: '0.4rem' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem', color: 'var(--hud-text-muted)' }}>
                  <span>Volume</span>
                  <span style={{ fontFamily: 'var(--hud-font-mono)' }}>{settings.soundVolume}%</span>
                </div>
                <input
                  type="range"
                  min="0"
                  max="100"
                  step="5"
                  value={settings.soundVolume}
                  onChange={handleVolumeChange}
                  style={{ width: '100%', accentColor: 'var(--hud-primary)' }}
                />
              </div>
            )}
          </div>

          {/* Voice & Speech Interface */}
          <div className="setting-group" style={{ border: '1px solid rgba(56, 189, 248, 0.25)', padding: '0.65rem', borderRadius: '4px', background: 'rgba(56, 189, 248, 0.05)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
              <label className="setting-label" style={{ margin: 0, color: '#38bdf8' }}>
                Voice & Speech Subsystem
              </label>
              <button
                type="button"
                className="hud-btn"
                onClick={handleTestVoice}
                style={{ fontSize: '0.7rem', padding: '0.2rem 0.6rem', borderColor: '#38bdf8' }}
              >
                {isTestingVoice ? '⏹ Stop Test' : '▶ Test Voice'}
              </button>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem', marginBottom: '0.6rem' }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', cursor: 'pointer', fontSize: '0.78rem' }}>
                <input
                  type="checkbox"
                  checked={settings.voice.voiceOutputEnabled}
                  onChange={handleVoiceOutputToggle}
                  style={{ accentColor: 'var(--hud-primary)' }}
                />
                <span>Spoken TTS Output</span>
              </label>

              <label style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', cursor: 'pointer', fontSize: '0.78rem' }}>
                <input
                  type="checkbox"
                  checked={settings.voice.autoPlayback}
                  onChange={handleAutoPlaybackToggle}
                  disabled={!settings.voice.voiceOutputEnabled}
                  style={{ accentColor: 'var(--hud-primary)' }}
                />
                <span>Auto-play Responses</span>
              </label>

              <label style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', cursor: 'pointer', fontSize: '0.78rem' }}>
                <input
                  type="checkbox"
                  checked={settings.voice.speechInputEnabled}
                  onChange={handleVoiceInputToggle}
                  style={{ accentColor: 'var(--hud-primary)' }}
                />
                <span>Push-to-Talk Mic (STT)</span>
              </label>
            </div>

            {/* Voice Library: Providers & Profiles */}
            {settings.voice.voiceOutputEnabled && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.55rem', marginTop: '0.4rem' }}>
                {/* TTS Engine Status Badges */}
                <div style={{ padding: '0.45rem 0.55rem', background: 'rgba(0, 0, 0, 0.3)', borderRadius: '3px', border: '1px solid rgba(56, 189, 248, 0.15)' }}>
                  <div style={{ fontSize: '0.68rem', color: 'var(--hud-text-muted)', marginBottom: '0.3rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                    TTS Engine Status
                  </div>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.4rem' }} data-testid="tts-engine-badges">
                    {ttsProviders.length > 0 ? (
                      ttsProviders.map((p) => {
                        let badgeColor = '#94a3b8';
                        let statusLabel = p.status as string;
                        if (p.status === 'installed_ready') {
                          badgeColor = '#22c55e';
                          statusLabel = 'Installed & Ready';
                        } else if (p.status === 'not_installed') {
                          badgeColor = '#f59e0b';
                          statusLabel = 'Not Installed';
                        } else if (p.status === 'unavailable') {
                          badgeColor = '#eab308';
                          statusLabel = 'Offline';
                        } else if (p.status === 'error') {
                          badgeColor = '#ef4444';
                          statusLabel = 'Error';
                        }
                        return (
                          <div
                            key={p.id}
                            title={p.error_message || `${p.name} (${p.voice_count} voices available)`}
                            style={{
                              display: 'inline-flex',
                              alignItems: 'center',
                              gap: '0.35rem',
                              fontSize: '0.68rem',
                              padding: '0.2rem 0.5rem',
                              borderRadius: '2px',
                              background: 'rgba(15, 23, 42, 0.7)',
                              border: `1px solid ${badgeColor}40`,
                              color: 'var(--hud-text)',
                            }}
                          >
                            <span style={{ width: '6px', height: '6px', borderRadius: '50%', background: badgeColor }} />
                            <span style={{ fontWeight: 600 }}>{p.name}:</span>
                            <span style={{ color: badgeColor }}>{statusLabel}</span>
                          </div>
                        );
                      })
                    ) : (
                      <span style={{ fontSize: '0.68rem', color: 'var(--hud-text-muted)' }}>Querying TTS engines...</span>
                    )}
                  </div>
                </div>

                {/* Voice Profile Selector */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.3rem' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem', color: 'var(--hud-text-muted)' }}>
                    <span style={{ color: '#38bdf8', fontWeight: 600 }}>Active Voice Profile</span>
                    <span style={{ fontFamily: 'var(--hud-font-mono)', fontSize: '0.68rem' }}>
                      {(voiceProfiles.find((p) => p.id === (settings.voice.activeProfileId || 'jarvis-default'))?.provider_id || 'sapi5').toUpperCase()}
                    </span>
                  </div>
                  <select
                    data-testid="voice-profile-select"
                    value={settings.voice.activeProfileId || 'jarvis-default'}
                    onChange={handleProfileChange}
                    style={{
                      background: 'rgba(0, 0, 0, 0.6)',
                      border: '1px solid var(--hud-dim)',
                      color: 'var(--hud-text)',
                      padding: '0.35rem 0.5rem',
                      fontFamily: 'var(--hud-font-mono)',
                      fontSize: '0.75rem',
                      borderRadius: '2px',
                      outline: 'none',
                    }}
                  >
                    {voiceProfiles.length > 0 ? (
                      voiceProfiles.map((p) => (
                        <option key={p.id} value={p.id} style={{ background: '#0a1628', color: '#fff' }}>
                          {p.name} [{p.provider_id.toUpperCase()}]{p.is_fallback ? ' ★ Fallback' : ''}
                        </option>
                      ))
                    ) : (
                      <option value="jarvis-default" style={{ background: '#0a1628', color: '#fff' }}>
                        J.A.R.V.I.S. Standard (SAPI 5) ★ Fallback
                      </option>
                    )}
                  </select>
                  <div style={{ fontSize: '0.66rem', color: 'var(--hud-text-muted)', lineHeight: '1.2' }}>
                    If an offline or uninstalled engine profile is selected, synthesis automatically routes to the SAPI fallback profile.
                  </div>
                </div>

                {/* External Voice Models Storage & In-App Import */}
                <div style={{ marginTop: '0.2rem', padding: '0.45rem', background: 'rgba(0, 0, 0, 0.35)', borderRadius: '3px', border: '1px solid rgba(56, 189, 248, 0.2)' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.35rem' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                      <span style={{ fontSize: '0.72rem', color: '#38bdf8', fontWeight: 600 }}>External Voice Models Storage</span>
                      <span
                        style={{
                          fontSize: '0.58rem',
                          padding: '0.1rem 0.35rem',
                          borderRadius: '2px',
                          fontWeight: 700,
                          background: modelsStatus?.is_external ? 'rgba(34, 197, 94, 0.15)' : 'rgba(234, 179, 8, 0.15)',
                          color: modelsStatus?.is_external ? '#4ade80' : '#facc15',
                          border: `1px solid ${modelsStatus?.is_external ? 'rgba(34, 197, 94, 0.3)' : 'rgba(234, 179, 8, 0.3)'}`,
                        }}
                      >
                        {modelsStatus?.is_external ? '✓ EXTERNAL (GitHub-Safe)' : '⚠ LOCAL (Git-Tracked)'}
                      </span>
                    </div>
                    <span style={{ fontSize: '0.64rem', color: 'var(--hud-text-muted)', fontFamily: 'var(--hud-font-mono)' }}>
                      Total: {modelsStatus?.total_size_mb || 0} MB
                    </span>
                  </div>

                  {/* Telemetry counters */}
                  <div style={{ display: 'flex', gap: '0.3rem', marginBottom: '0.4rem', flexWrap: 'wrap' }}>
                    <span style={{ fontSize: '0.62rem', background: 'rgba(56, 189, 248, 0.08)', padding: '0.1rem 0.35rem', borderRadius: '2px', border: '1px solid rgba(56, 189, 248, 0.15)', color: '#bae6fd' }}>
                      STT Models: {modelsStatus?.stt_models_count ?? 0}
                    </span>
                    <span style={{ fontSize: '0.62rem', background: 'rgba(56, 189, 248, 0.08)', padding: '0.1rem 0.35rem', borderRadius: '2px', border: '1px solid rgba(56, 189, 248, 0.15)', color: '#bae6fd' }}>
                      Piper Voicepacks: {modelsStatus?.tts_voicepacks_count ?? 0}
                    </span>
                    <span style={{ fontSize: '0.62rem', background: 'rgba(56, 189, 248, 0.08)', padding: '0.1rem 0.35rem', borderRadius: '2px', border: '1px solid rgba(56, 189, 248, 0.15)', color: '#bae6fd' }}>
                      RVC Character Voices: {modelsStatus?.rvc_models_count ?? 0}
                    </span>
                  </div>

                  {/* Active Directory Configuration */}
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '0.2rem', marginBottom: '0.4rem' }}>
                    <div style={{ fontSize: '0.64rem', color: 'var(--hud-text-muted)' }}>
                      Active Storage Location (Whisper STT, Piper ONNX, RVC):
                    </div>
                    <div style={{ display: 'flex', gap: '0.3rem' }}>
                      <input
                        type="text"
                        value={externalPathInput}
                        onChange={(e) => setExternalPathInput(e.target.value)}
                        placeholder="e.g. D:\Raihan\JARVIS_MODELS"
                        className="jarvis-input"
                        style={{
                          flex: 1,
                          fontSize: '0.68rem',
                          padding: '0.2rem 0.4rem',
                          background: 'rgba(10, 22, 40, 0.8)',
                          border: '1px solid rgba(56, 189, 248, 0.25)',
                          borderRadius: '2px',
                          color: '#f8fafc',
                          fontFamily: 'var(--hud-font-mono)',
                        }}
                      />
                      <button
                        type="button"
                        onClick={handleConfigureModelsPath}
                        disabled={isConfiguringPath || !externalPathInput.trim()}
                        className="hud-btn"
                        style={{
                          fontSize: '0.66rem',
                          padding: '0.2rem 0.5rem',
                          borderColor: '#38bdf8',
                          cursor: isConfiguringPath ? 'not-allowed' : 'pointer',
                        }}
                      >
                        {isConfiguringPath ? 'Saving...' : 'Set Folder'}
                      </button>
                    </div>
                  </div>

                  {/* In-App Direct Path Import */}
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '0.2rem' }}>
                    <div style={{ fontSize: '0.64rem', color: 'var(--hud-text-muted)' }}>
                      Import Model from Local PC Path (.onnx, .pth, or folder):
                    </div>
                    <div style={{ display: 'flex', gap: '0.3rem' }}>
                      <input
                        type="text"
                        value={importPathInput}
                        onChange={(e) => setImportPathInput(e.target.value)}
                        placeholder="Path to .pth/.onnx file or character folder outside JARVIS"
                        className="jarvis-input"
                        style={{
                          flex: 2,
                          fontSize: '0.68rem',
                          padding: '0.2rem 0.4rem',
                          background: 'rgba(10, 22, 40, 0.8)',
                          border: '1px solid rgba(56, 189, 248, 0.25)',
                          borderRadius: '2px',
                          color: '#f8fafc',
                          fontFamily: 'var(--hud-font-mono)',
                        }}
                      />
                      <input
                        type="text"
                        value={importPathNameInput}
                        onChange={(e) => setImportPathNameInput(e.target.value)}
                        placeholder="Name (opt)"
                        className="jarvis-input"
                        style={{
                          flex: 1,
                          fontSize: '0.68rem',
                          padding: '0.2rem 0.4rem',
                          background: 'rgba(10, 22, 40, 0.8)',
                          border: '1px solid rgba(56, 189, 248, 0.25)',
                          borderRadius: '2px',
                          color: '#f8fafc',
                        }}
                      />
                      <button
                        type="button"
                        onClick={handleImportFromPath}
                        disabled={isImportingPath || !importPathInput.trim()}
                        className="hud-btn"
                        style={{
                          fontSize: '0.66rem',
                          padding: '0.2rem 0.5rem',
                          borderColor: '#38bdf8',
                          cursor: isImportingPath ? 'not-allowed' : 'pointer',
                        }}
                      >
                        {isImportingPath ? 'Importing...' : '📁 Import Path'}
                      </button>
                    </div>
                  </div>

                  {modelsMsg && (
                    <div style={{ fontSize: '0.68rem', color: '#38bdf8', marginTop: '0.3rem', fontFamily: 'var(--hud-font-mono)' }}>
                      {modelsMsg}
                    </div>
                  )}
                </div>

                {/* Pretrained Voicepacks & Community Models */}
                <div style={{ marginTop: '0.2rem', padding: '0.45rem', background: 'rgba(0, 0, 0, 0.35)', borderRadius: '3px', border: '1px solid rgba(56, 189, 248, 0.2)' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.35rem' }}>
                    <span style={{ fontSize: '0.72rem', color: '#38bdf8', fontWeight: 600 }}>Pretrained Voicepacks</span>
                    <label
                      className="hud-btn"
                      style={{
                        fontSize: '0.66rem',
                        padding: '0.18rem 0.5rem',
                        borderColor: '#38bdf8',
                        cursor: isImportingVoicepack ? 'not-allowed' : 'pointer',
                        display: 'inline-flex',
                        alignItems: 'center',
                        gap: '0.3rem',
                      }}
                    >
                      <input
                        type="file"
                        accept=".zip"
                        onChange={handleVoicepackUpload}
                        disabled={isImportingVoicepack}
                        style={{ display: 'none' }}
                      />
                      {isImportingVoicepack ? '⏳ Importing...' : '📁 Import Voicepack (.zip)'}
                    </label>
                  </div>

                  {voicepackStatusMsg && (
                    <div style={{ fontSize: '0.68rem', color: '#38bdf8', marginBottom: '0.3rem', fontFamily: 'var(--hud-font-mono)' }}>
                      {voicepackStatusMsg}
                    </div>
                  )}

                  <div style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem', maxHeight: '110px', overflowY: 'auto' }}>
                    {voicepacks.length > 0 ? (
                      voicepacks.map((vp) => (
                        <div
                          key={vp.id}
                          style={{
                            display: 'flex',
                            justifyContent: 'space-between',
                            alignItems: 'center',
                            fontSize: '0.68rem',
                            padding: '0.22rem 0.4rem',
                            background: 'rgba(15, 23, 42, 0.6)',
                            borderRadius: '2px',
                            border: '1px solid rgba(56, 189, 248, 0.12)',
                          }}
                        >
                          <div style={{ display: 'flex', flexDirection: 'column' }}>
                            <span style={{ fontWeight: 600, color: '#f8fafc' }}>{vp.name}</span>
                            <span style={{ fontSize: '0.62rem', color: 'var(--hud-text-muted)' }}>
                              {vp.provider_id.toUpperCase()} • {vp.language} • {Math.round(vp.sample_rate / 1000)}kHz
                            </span>
                          </div>
                          {!vp.is_builtin && (
                            <button
                              type="button"
                              onClick={() => handleDeleteVoicepack(vp.id)}
                              title="Delete this voicepack from disk"
                              style={{
                                background: 'transparent',
                                border: 'none',
                                color: '#ef4444',
                                cursor: 'pointer',
                                fontSize: '0.68rem',
                                padding: '0.1rem 0.3rem',
                              }}
                            >
                              ✕
                            </button>
                          )}
                        </div>
                      ))
                    ) : (
                      <div style={{ fontSize: '0.66rem', color: 'var(--hud-text-muted)', fontStyle: 'italic' }}>
                        No local voicepacks imported yet. Click "Import Voicepack (.zip)" to install a model.
                      </div>
                    )}
                  </div>
                </div>

                {/* Voice Selection Dropdown */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.3rem', marginTop: '0.2rem' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem', color: 'var(--hud-text-muted)' }}>
                    <span>Synthesized Voice</span>
                    <span style={{ fontFamily: 'var(--hud-font-mono)' }}>Windows SAPI / OneCore</span>
                  </div>
                  <select
                    value={settings.voice.selectedVoiceId}
                    onChange={handleVoiceChange}
                    style={{
                      background: 'rgba(0, 0, 0, 0.6)',
                      border: '1px solid var(--hud-dim)',
                      color: 'var(--hud-text)',
                      padding: '0.35rem 0.5rem',
                      fontFamily: 'var(--hud-font-mono)',
                      fontSize: '0.75rem',
                      borderRadius: '2px',
                      outline: 'none',
                    }}
                  >
                    {availableVoices.length > 0 ? (
                      availableVoices.map((v) => (
                        <option key={v.id} value={v.id} style={{ background: '#0a1628', color: '#fff' }}>
                          {v.name} ({v.gender || 'Standard'}) {v.is_default ? '★ Default' : ''}
                        </option>
                      ))
                    ) : (
                      <option value="" style={{ background: '#0a1628', color: '#fff' }}>
                        Default Windows Synthesizer
                      </option>
                    )}
                  </select>
                </div>

                {/* Speaking Rate */}
                <div style={{ marginTop: '0.3rem' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem', color: 'var(--hud-text-muted)' }}>
                    <span>Speaking Speed</span>
                    <span style={{ fontFamily: 'var(--hud-font-mono)' }}>{settings.voice.speakingRate} WPM</span>
                  </div>
                  <input
                    type="range"
                    min="100"
                    max="250"
                    step="10"
                    value={settings.voice.speakingRate}
                    onChange={handleSpeakingRateChange}
                    style={{ width: '100%', accentColor: 'var(--hud-primary)' }}
                  />
                </div>

                {/* Voice Volume */}
                <div style={{ marginTop: '0.3rem' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem', color: 'var(--hud-text-muted)' }}>
                    <span>Voice Volume</span>
                    <span style={{ fontFamily: 'var(--hud-font-mono)' }}>{settings.voice.volume}%</span>
                  </div>
                  <input
                    type="range"
                    min="0"
                    max="100"
                    step="5"
                    value={settings.voice.volume}
                    onChange={handleVoiceVolumeChange}
                    style={{ width: '100%', accentColor: 'var(--hud-primary)' }}
                  />
                </div>

                {/* Voice Pitch */}
                <div style={{ marginTop: '0.3rem' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem', color: 'var(--hud-text-muted)' }}>
                    <span>Voice Pitch / Semitone Key</span>
                    <span style={{ fontFamily: 'var(--hud-font-mono)' }}>
                      {(settings.voice.pitch ?? 1.0) === 1.0
                        ? '1.0x (Normal / 0 st)'
                        : `${(settings.voice.pitch ?? 1.0).toFixed(2)}x (${Math.round(12 * Math.log2(settings.voice.pitch ?? 1.0)) > 0 ? '+' : ''}${Math.round(12 * Math.log2(settings.voice.pitch ?? 1.0))} st)`}
                    </span>
                  </div>
                  <input
                    type="range"
                    min="0.5"
                    max="2.0"
                    step="0.05"
                    value={settings.voice.pitch ?? 1.0}
                    onChange={handlePitchChange}
                    style={{ width: '100%', accentColor: 'var(--hud-primary)' }}
                  />
                </div>

                {/* Conversational Delivery Style (Milestone 2.5) */}
                <div style={{ marginTop: '0.4rem', borderTop: '1px dashed rgba(56, 189, 248, 0.25)', paddingTop: '0.4rem' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem', color: 'var(--hud-text-muted)', marginBottom: '0.3rem' }}>
                    <span style={{ color: '#38bdf8', fontWeight: 600 }}>Conversational Delivery Style</span>
                    <span style={{ fontFamily: 'var(--hud-font-mono)', fontSize: '0.68rem' }}>Prosody & Pauses</span>
                  </div>
                  <div style={{ display: 'flex', gap: '0.4rem' }}>
                    {(['relaxed', 'conversational', 'formal'] as DeliveryProfile[]).map((profKey) => {
                      const cfg = DELIVERY_PROFILES[profKey];
                      const active = (settings.voice.deliveryProfile || 'relaxed') === profKey;
                      return (
                        <button
                          key={profKey}
                          type="button"
                          className={`sim-btn ${active ? 'active' : ''}`}
                          onClick={() => handleDeliveryProfileChange(profKey)}
                          title={cfg.description}
                          style={{
                            flex: 1,
                            fontSize: '0.68rem',
                            padding: '0.3rem 0.4rem',
                            display: 'flex',
                            flexDirection: 'column',
                            alignItems: 'center',
                            gap: '0.15rem',
                          }}
                        >
                          <span style={{ fontWeight: 600, textTransform: 'capitalize' }}>{profKey}</span>
                          <span style={{ fontSize: '0.6rem', color: active ? 'inherit' : 'var(--hud-text-muted)' }}>
                            {profKey === 'relaxed' ? 'Calm (Default)' : profKey === 'conversational' ? 'Everyday' : 'Deliberate'}
                          </span>
                        </button>
                      );
                    })}
                  </div>
                  <div style={{ fontSize: '0.66rem', color: 'var(--hud-text-muted)', marginTop: '0.25rem', lineHeight: '1.2' }}>
                    {DELIVERY_PROFILES[settings.voice.deliveryProfile || 'relaxed']?.description}
                  </div>
                </div>
              </div>
            )}

            {/* STT Whisper Model Selector */}
            {settings.voice.speechInputEnabled && (
              <div style={{ marginTop: '0.5rem', borderTop: '1px dashed rgba(56, 189, 248, 0.25)', paddingTop: '0.5rem' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem', color: 'var(--hud-text-muted)', marginBottom: '0.25rem' }}>
                  <span>Speech-to-Text Model (Faster-Whisper)</span>
                  <span style={{ fontFamily: 'var(--hud-font-mono)', color: '#38bdf8' }}>100% On-Device</span>
                </div>
                <select
                  value={settings.voice.sttModelSize || 'base.en'}
                  onChange={handleSTTModelChange}
                  style={{
                    width: '100%',
                    background: 'rgba(0, 0, 0, 0.6)',
                    border: '1px solid var(--hud-dim)',
                    color: 'var(--hud-text)',
                    padding: '0.35rem 0.5rem',
                    fontFamily: 'var(--hud-font-mono)',
                    fontSize: '0.75rem',
                    borderRadius: '2px',
                    outline: 'none',
                  }}
                >
                  <option value="base.en" style={{ background: '#0a1628', color: '#fff' }}>
                    base.en — High Accuracy & Vocabulary (Recommended, ~140 MB)
                  </option>
                  <option value="tiny.en" style={{ background: '#0a1628', color: '#fff' }}>
                    tiny.en — Ultra-Fast Lightweight (~75 MB)
                  </option>
                  <option value="small.en" style={{ background: '#0a1628', color: '#fff' }}>
                    small.en — Maximum Linguistic Depth (High CPU, ~480 MB)
                  </option>
                </select>
                <div style={{ fontSize: '0.68rem', color: 'var(--hud-text-muted)', marginTop: '0.2rem' }}>
                  Conditioned for J.A.R.V.I.S., Notepad, Calculator, Chrome, PowerShell, and desktop control commands.
                </div>
              </div>
            )}
          </div>

          {/* Custom Keybindings & Shortcuts */}
          <div className="setting-group" style={{ border: '1px solid rgba(0, 229, 255, 0.25)', padding: '0.65rem', borderRadius: '4px', background: 'rgba(0, 229, 255, 0.04)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
              <label className="setting-label" style={{ margin: 0, color: 'var(--hud-primary)' }}>
                Custom Keybindings & Global Shortcuts
              </label>
              <button
                type="button"
                className="hud-btn"
                onClick={handleResetKeybinds}
                style={{ fontSize: '0.7rem', padding: '0.2rem 0.6rem' }}
                title="Reset all shortcuts to factory defaults"
              >
                ↺ Reset Shortcuts
              </button>
            </div>

            {keybindConflict && (
              <div style={{ background: 'rgba(239, 68, 68, 0.15)', border: '1px solid #ef4444', color: '#fca5a5', padding: '0.4rem 0.6rem', borderRadius: '3px', fontSize: '0.72rem', marginBottom: '0.5rem' }}>
                ⚠ Shortcut Conflict: {keybindConflict}
              </div>
            )}

            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.45rem' }}>
              {KEYBIND_ACTIONS.map((action) => {
                const isRecordingThis = recordingKeybindAction === action.key;
                const currentBinds = settings.keybinds || DEFAULT_KEYBINDS;
                const currentValue = currentBinds[action.key] || DEFAULT_KEYBINDS[action.key];
                return (
                  <div
                    key={action.key}
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                      background: 'rgba(0,0,0,0.3)',
                      padding: '0.4rem 0.6rem',
                      borderRadius: '3px',
                      border: isRecordingThis ? '1px solid var(--hud-primary)' : '1px solid rgba(255,255,255,0.06)',
                    }}
                  >
                    <div>
                      <div style={{ fontSize: '0.78rem', color: 'var(--hud-text)', fontWeight: 500 }}>{action.label}</div>
                      <div style={{ fontSize: '0.68rem', color: 'var(--hud-text-muted)' }}>{action.description}</div>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                      <span
                        style={{
                          fontFamily: 'var(--hud-font-mono)',
                          fontSize: '0.75rem',
                          background: isRecordingThis ? 'rgba(0, 229, 255, 0.2)' : 'rgba(255,255,255,0.08)',
                          color: isRecordingThis ? 'var(--hud-primary)' : '#fff',
                          border: isRecordingThis ? '1px dashed var(--hud-primary)' : '1px solid rgba(255,255,255,0.15)',
                          padding: '0.2rem 0.5rem',
                          borderRadius: '3px',
                          minWidth: '70px',
                          textAlign: 'center',
                        }}
                      >
                        {isRecordingThis ? 'Press Key...' : currentValue}
                      </span>
                      <button
                        type="button"
                        className={`sim-btn ${isRecordingThis ? 'active' : ''}`}
                        onClick={() => handleStartRecordingKeybind(action.key)}
                        style={{ fontSize: '0.7rem', padding: '0.2rem 0.5rem' }}
                      >
                        {isRecordingThis ? 'Cancel' : 'Set Key'}
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
            <div style={{ fontSize: '0.68rem', color: 'var(--hud-text-muted)', marginTop: '0.4rem' }}>
              Note: Shortcuts work inside the app and globally across Windows when the desktop shell is active. Escape is restricted to in-app cancel to protect Windows OS shortcuts.
            </div>
          </div>

          {/* Panel Visibility Toggles */}
          <div className="setting-group">
            <label className="setting-label">Modular Panel Visibility</label>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem' }}>
              {(Object.keys(settings.panels) as PanelId[]).map((pid) => {
                const p = settings.panels[pid];
                return (
                  <label
                    key={pid}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '0.5rem',
                      fontFamily: 'var(--hud-font-mono)',
                      fontSize: '0.75rem',
                      color: p.visible ? 'var(--hud-text)' : 'var(--hud-text-muted)',
                      cursor: 'pointer',
                    }}
                  >
                    <input
                      type="checkbox"
                      checked={p.visible}
                      onChange={(e) => handlePanelVisibility(pid, e.target.checked)}
                      style={{ accentColor: 'var(--hud-primary)' }}
                    />
                    <span>{p.title}</span>
                  </label>
                );
              })}
            </div>
          </div>

          {/* Reset to defaults */}
          <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '1rem', paddingTop: '1rem', borderTop: '1px solid var(--hud-dim)' }}>
            <button className="hud-btn danger" onClick={onResetDefaults}>
              Reset to Factory Defaults
            </button>
            <button className="hud-btn" onClick={onClose}>
              Apply & Close
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
