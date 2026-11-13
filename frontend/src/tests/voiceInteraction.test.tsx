import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { cleanTextForSpeech } from '../services/voiceService';
import { isValidStateTransition, ASSISTANT_STATE_META } from '../types/assistantState';
import { DEFAULT_SETTINGS, loadSettings, saveSettings } from '../types/settings';
import { ArcReactor } from '../components/ArcReactor';
import { QuickCommandBar } from '../components/QuickCommandBar';
import { SettingsModal } from '../components/SettingsModal';
import * as api from '../services/api';

describe('Voice Subsystem Text Sanitizer', () => {
  it('strips code blocks, raw URLs, and markdown formatting for natural speech', () => {
    const rawMarkdown = `
# Heading 1
Here is **important** text and [a link](https://example.com/docs).
Check out this code:
\`\`\`python
def hello():
    print("world")
\`\`\`
Use \`variable_name\` here. Visit https://antigravity.google.com for info.
- Bullet item 1
- Bullet item 2
`;
    const cleaned = cleanTextForSpeech(rawMarkdown);

    // Code blocks should be replaced or omitted
    expect(cleaned).not.toContain('def hello()');
    // URLs should be removed
    expect(cleaned).not.toContain('https://example.com/docs');
    expect(cleaned).not.toContain('https://antigravity.google.com');
    // Markdown symbols stripped
    expect(cleaned).not.toContain('**important**');
    expect(cleaned).toContain('important text and a link');
    expect(cleaned).toContain('variable_name');
    expect(cleaned).toContain('Bullet item 1');
  });

  it('handles empty or whitespace strings safely', () => {
    expect(cleanTextForSpeech('')).toBe('');
    expect(cleanTextForSpeech('   \n\t  ')).toBe('');
  });
});

describe('Assistant State Machine - SPEAKING State', () => {
  it('defines SPEAKING metadata with cyan theme and vocal label', () => {
    const meta = ASSISTANT_STATE_META.SPEAKING;
    expect(meta).toBeDefined();
    expect(meta.label).toBe('VOCAL SYNTHESIS ACTIVE');
    expect(meta.code).toBe('SPEAKING');
  });

  it('allows valid transitions into and out of SPEAKING', () => {
    expect(isValidStateTransition('IDLE', 'SPEAKING')).toBe(true);
    expect(isValidStateTransition('RESPONDING', 'SPEAKING')).toBe(true);
    expect(isValidStateTransition('SPEAKING', 'IDLE')).toBe(true);
    expect(isValidStateTransition('SPEAKING', 'LISTENING')).toBe(true);
    expect(isValidStateTransition('SPEAKING', 'ERROR')).toBe(true);
  });
});

describe('Voice Settings Persistence', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('provides sensible default voice settings', () => {
    expect(DEFAULT_SETTINGS.voice).toBeDefined();
    expect(DEFAULT_SETTINGS.voice.voiceOutputEnabled).toBe(true);
    expect(DEFAULT_SETTINGS.voice.speechInputEnabled).toBe(true);
    expect(DEFAULT_SETTINGS.voice.speakingRate).toBe(180);
    expect(DEFAULT_SETTINGS.voice.volume).toBe(100);
    expect(DEFAULT_SETTINGS.voice.autoPlayback).toBe(true);
  });

  it('persists and reloads voice settings correctly', () => {
    const customSettings = {
      ...DEFAULT_SETTINGS,
      voice: {
        voiceOutputEnabled: false,
        speechInputEnabled: true,
        selectedVoiceId: 'test-voice-id',
        speakingRate: 150,
        volume: 75,
        autoPlayback: false,
      },
    };

    saveSettings(customSettings);
    const loaded = loadSettings();

    expect(loaded.voice.voiceOutputEnabled).toBe(false);
    expect(loaded.voice.selectedVoiceId).toBe('test-voice-id');
    expect(loaded.voice.speakingRate).toBe(150);
    expect(loaded.voice.volume).toBe(75);
    expect(loaded.voice.autoPlayback).toBe(false);
  });
});

describe('ArcReactor Voice State Visuals', () => {
  it('displays SPEAKING label when assistantState is SPEAKING', () => {
    render(<ArcReactor assistantState="SPEAKING" latencyMs={45} />);
    expect(screen.getByText('SPEAKING')).not.toBeNull();
  });

  it('triggers onStopSpeaking callback when clicked while speaking', () => {
    const onStopSpeaking = vi.fn();
    render(<ArcReactor assistantState="SPEAKING" latencyMs={45} onStopSpeaking={onStopSpeaking} />);

    const reactor = screen.getByRole('button');
    fireEvent.click(reactor);

    expect(onStopSpeaking).toHaveBeenCalledTimes(1);
  });
});

describe('QuickCommandBar Voice Integration', () => {
  it('renders push-to-talk microphone button and triggers stop speaking when active', () => {
    const onStopSpeaking = vi.fn();
    render(
      <QuickCommandBar
        onOpenDashboard={vi.fn()}
        onClose={vi.fn()}
        isSpeaking={true}
        onStopSpeaking={onStopSpeaking}
        speechInputEnabled={true}
      />
    );

    // Should have Push-to-Talk button
    const micBtn = screen.getByTitle('Push-to-Talk (Microphone input)');
    expect(micBtn).not.toBeNull();

    // Should have Silence / Stop Speaking button
    const muteBtn = screen.getByTitle('Silence Voice Output (Stop Speaking)');
    expect(muteBtn).not.toBeNull();

    fireEvent.click(muteBtn);
    expect(onStopSpeaking).toHaveBeenCalledTimes(1);
  });
});

describe('SettingsModal Voice Configuration Panel', () => {
  beforeEach(() => {
    vi.spyOn(api, 'fetchVoiceList').mockResolvedValue({
      voices: [
        { id: 'v1', name: 'Microsoft David', gender: 'Male', languages: ['en-US'], is_default: true },
        { id: 'v2', name: 'Microsoft Zira', gender: 'Female', languages: ['en-US'], is_default: false },
      ],
      default_voice_id: 'v1',
    });
  });

  it('renders Voice & Speech Subsystem controls and updates settings', () => {
    const onUpdate = vi.fn();
    render(
      <SettingsModal
        isOpen={true}
        settings={DEFAULT_SETTINGS}
        onUpdateSettings={onUpdate}
        onResetDefaults={vi.fn()}
        onClose={vi.fn()}
      />
    );

    expect(screen.getByText('Voice & Speech Subsystem')).not.toBeNull();
    expect(screen.getByText('Spoken TTS Output')).not.toBeNull();
    expect(screen.getByText('Push-to-Talk Mic (STT)')).not.toBeNull();
    expect(screen.getByText('Speaking Speed')).not.toBeNull();
    expect(screen.getByText('Voice Volume')).not.toBeNull();
  });
});
