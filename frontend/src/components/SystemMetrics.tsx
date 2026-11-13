import React from 'react';
import { HealthResponse } from '../types/health';

interface SystemMetricsProps {
  healthData: HealthResponse | null;
  latencyMs: number | null;
}

export const SystemMetrics: React.FC<SystemMetricsProps> = ({ healthData, latencyMs }) => {
  return (
    <div className="hud-panel">
      <div className="panel-header">
        <span className="panel-title">Host Telemetry</span>
      </div>

      <div className="telemetry-row">
        <span className="telemetry-label">Host Loopback:</span>
        <span className="telemetry-value highlight">
          {healthData ? `${healthData.system.host}:${healthData.system.port}` : '--'}
        </span>
      </div>

      <div className="telemetry-row">
        <span className="telemetry-label">OS Platform:</span>
        <span className="telemetry-value">
          {healthData ? `${healthData.system.os} ${healthData.system.os_release}` : '--'}
        </span>
      </div>

      <div className="telemetry-row">
        <span className="telemetry-label">Python Runtime:</span>
        <span className="telemetry-value">
          {healthData ? `v${healthData.system.python}` : '--'}
        </span>
      </div>

      <div className="telemetry-row">
        <span className="telemetry-label">Uptime:</span>
        <span className="telemetry-value">
          {healthData ? `${healthData.uptime_seconds}s` : '--'}
        </span>
      </div>

      <div className="telemetry-row">
        <span className="telemetry-label">Ping Latency:</span>
        <span className="telemetry-value highlight">
          {latencyMs !== null ? `${latencyMs} ms` : '--'}
        </span>
      </div>

      <div className="telemetry-row">
        <span className="telemetry-label">Security Tier:</span>
        <span className="telemetry-value" style={{ color: '#34d399' }}>
          SANDBOX ENFORCED
        </span>
      </div>
    </div>
  );
};

