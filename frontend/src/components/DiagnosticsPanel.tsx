import React from 'react';
import { HealthResponse } from '../types/health';

interface DiagnosticsPanelProps {
  healthData: HealthResponse | null;
}

export const DiagnosticsPanel: React.FC<DiagnosticsPanelProps> = ({ healthData }) => {
  if (!healthData) {
    return (
      <div className="hud-panel">
        <div className="panel-header">
          <span className="panel-title">Diagnostic Stream</span>
        </div>
        <p style={{ color: 'var(--hud-text-muted)', fontSize: '0.85rem' }}>
          Awaiting backend telemetry response...
        </p>
      </div>
    );
  }

  const { subsystems } = healthData;

  return (
    <div className="hud-panel">
      <div className="panel-header">
        <span className="panel-title">Subsystem Integrity</span>
        <span style={{ fontSize: '0.75rem', color: 'var(--hud-cyan)' }}>V.{healthData.version}</span>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem' }}>
        <div className="subsystem-item">
          <span className="subsystem-name">SQLite Data Store</span>
          <span className={`subsystem-badge ${subsystems.database.status}`}>
            {subsystems.database.status}
          </span>
        </div>

        <div className="subsystem-item">
          <span className="subsystem-name">Security Sandbox</span>
          <span className={`subsystem-badge ${subsystems.security.status}`}>
            {subsystems.security.status}
          </span>
        </div>

        <div className="subsystem-item">
          <span className="subsystem-name">AI Provider (Gemini)</span>
          <span className={`subsystem-badge ${subsystems.ai_provider.status}`}>
            {subsystems.ai_provider.status}
          </span>
        </div>

        <div className="subsystem-item">
          <span className="subsystem-name">Windows UIA Engine</span>
          <span className={`subsystem-badge ${subsystems.automation.status}`}>
            {subsystems.automation.status}
          </span>
        </div>
      </div>

      <div style={{ marginTop: '0.5rem' }}>
        <div className="panel-header" style={{ marginBottom: '0.5rem' }}>
          <span className="panel-title" style={{ fontSize: '0.8rem' }}>Active Capabilities</span>
        </div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.35rem' }}>
          {healthData.capabilities.map((cap) => (
            <span
              key={cap}
              style={{
                fontSize: '0.7rem',
                padding: '0.2rem 0.5rem',
                background: 'rgba(0, 229, 255, 0.08)',
                border: '1px solid var(--hud-cyan-dim)',
                borderRadius: '2px',
                fontFamily: 'var(--hud-font-mono)',
              }}
            >
              {cap}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
};

