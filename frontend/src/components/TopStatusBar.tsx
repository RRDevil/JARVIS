import React, { useState, useEffect } from 'react';
import { AssistantState, ASSISTANT_STATE_META } from '../types/assistantState';
import { ConnectionState, HealthResponse } from '../types/health';
import { soundManager } from '../services/soundManager';

interface TopStatusBarProps {
  assistantState: AssistantState;
  connectionState: ConnectionState;
  healthData: HealthResponse | null;
  latencyMs: number | null;
  soundEnabled: boolean;
  onToggleSound: () => void;
  onOpenSettings: () => void;
  onOpenAppManager?: () => void;
  onShutdown?: () => void;
  onCollapseToOrb?: () => void;
  onSwitchToHUD?: () => void;
}

export const TopStatusBar: React.FC<TopStatusBarProps> = ({
  assistantState,
  connectionState,
  healthData,
  latencyMs,
  soundEnabled,
  onToggleSound,
  onOpenSettings,
  onOpenAppManager,
  onShutdown,
  onCollapseToOrb,
  onSwitchToHUD,
}) => {
  const [currentTime, setCurrentTime] = useState<string>('');

  useEffect(() => {
    const updateTime = () => {
      const now = new Date();
      setCurrentTime(
        `${now.toLocaleDateString(undefined, {
          weekday: 'short',
          month: 'short',
          day: 'numeric',
        })} // ${now.toLocaleTimeString(undefined, { hour12: false })}`
      );
    };
    updateTime();
    const timer = setInterval(updateTime, 1000);
    return () => clearInterval(timer);
  }, []);

  const meta = ASSISTANT_STATE_META[assistantState] || ASSISTANT_STATE_META.IDLE;

  const handleSoundClick = () => {
    soundManager.play('CLICK_CUE');
    onToggleSound();
  };

  const handleSettingsClick = () => {
    soundManager.play('CLICK_CUE');
    onOpenSettings();
  };

  return (
    <header className="top-status-bar pywebview-drag-region" role="banner">
      <div className="brand-section">
        <div>
          <h1 className="brand-title">J.A.R.V.I.S.</h1>
          <p className="brand-tagline">Autonomous Desktop Interface // Mark VII</p>
        </div>
      </div>

      <div className="top-bar-controls">
        <div className="digital-clock" title="Local System Clock">
          {currentTime || 'SYNCHRONIZING CLOCK...'}
        </div>

        <div
          className="state-badge"
          style={{
            border: `1px solid ${meta.color}`,
            background: `rgba(${meta.color === '#ef4444' ? '239, 68, 68' : '0, 229, 255'}, 0.08)`,
            color: meta.color,
          }}
          title={meta.description}
        >
          <span
            className="status-dot"
            style={{
              background: meta.color,
              boxShadow: `0 0 8px ${meta.glowColor}`,
            }}
          />
          <span>{meta.label}</span>
        </div>

        <div
          className="state-badge"
          style={{
            border: '1px solid var(--hud-dim)',
            background: 'rgba(0, 0, 0, 0.4)',
            color: connectionState === 'connected' ? '#34d399' : '#f87171',
          }}
          title={
            healthData
              ? `Backend Host: ${healthData.system.host}:${healthData.system.port} | Uptime: ${healthData.uptime_seconds}s`
              : 'Backend connection pending'
          }
        >
          <span
            className="status-dot"
            style={{
              background: connectionState === 'connected' ? '#10b981' : '#ef4444',
              boxShadow: `0 0 8px ${connectionState === 'connected' ? '#10b981' : '#ef4444'}`,
            }}
          />
          <span>
            {connectionState === 'connected'
              ? `CORE LINK [${latencyMs ?? '--'}ms]`
              : connectionState === 'connecting'
              ? 'LINK SYNC...'
              : 'LINK LOST'}
          </span>
        </div>

        <button
          className="hud-btn secondary"
          style={{ padding: '0.35rem 0.65rem', fontSize: '0.75rem' }}
          onClick={handleSoundClick}
          title={soundEnabled ? 'Mute Interface Sound Cues' : 'Enable Interface Sound Cues'}
          aria-label={soundEnabled ? 'Mute sound' : 'Enable sound'}
        >
          {soundEnabled ? 'AUDIO: ON' : 'AUDIO: MUTED'}
        </button>

        {onCollapseToOrb && (
          <button
            className="hud-btn secondary"
            style={{ padding: '0.35rem 0.65rem', fontSize: '0.75rem' }}
            onClick={onCollapseToOrb}
            title="Collapse to Floating Orb (Esc)"
          >
            − ORB
          </button>
        )}

        {onSwitchToHUD && (
          <button
            className="hud-btn secondary"
            style={{ padding: '0.35rem 0.65rem', fontSize: '0.75rem' }}
            onClick={onSwitchToHUD}
            title="Switch to Compact Floating HUD"
          >
            ▢ HUD
          </button>
        )}

        {onOpenAppManager && (
          <button
            className="hud-btn secondary"
            style={{ padding: '0.35rem 0.65rem', fontSize: '0.75rem', borderColor: 'rgba(0, 240, 255, 0.4)' }}
            onClick={() => {
              soundManager.play('CLICK_CUE');
              onOpenAppManager();
            }}
            title="Manage Integrated Desktop Applications (Opera GX, Office, Discord, etc.)"
            aria-label="Open integrated applications manager"
          >
            APPS
          </button>
        )}

        <button
          className="hud-btn"
          style={{ padding: '0.35rem 0.75rem', fontSize: '0.75rem' }}
          onClick={handleSettingsClick}
          title="Open Customization and Layout Settings"
          aria-label="Open settings"
        >
          CONFIG
        </button>

        {onShutdown && (
          <button
            className="hud-btn danger"
            style={{ padding: '0.35rem 0.75rem', fontSize: '0.75rem' }}
            onClick={onShutdown}
            title="Completely Terminate JARVIS and Exit All Background Services"
            aria-label="Exit JARVIS completely"
          >
            ⏻ EXIT
          </button>
        )}
      </div>
    </header>
  );
};

