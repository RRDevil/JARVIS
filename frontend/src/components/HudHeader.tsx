import React from 'react';
import { ConnectionState, HealthResponse } from '../types/health';

interface HudHeaderProps {
  connectionState: ConnectionState;
  healthData: HealthResponse | null;
  latencyMs: number | null;
}

export const HudHeader: React.FC<HudHeaderProps> = ({ connectionState, healthData, latencyMs }) => {
  return (
    <header className="hud-header">
      <div className="brand-section">
        <div>
          <h1 className="brand-title">J.A.R.V.I.S.</h1>
          <p className="brand-tagline">Advanced Autonomous Desktop Interface // Mark VII</p>
        </div>
      </div>

      <div className="status-badge">
        <span className={`status-dot ${connectionState}`} />
        <span>
          {connectionState === 'connected' && healthData
            ? `CORE OPERATIONAL [${latencyMs}ms]`
            : connectionState === 'connecting'
            ? 'CONNECTING TO CORE...'
            : 'CORE LINK SEVERED'}
        </span>
      </div>
    </header>
  );
};

