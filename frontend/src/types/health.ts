/**
 * Health and diagnostics response data types.
 */

export interface SubsystemStatus {
  status: string;
  details: Record<string, any>;
}

export interface HealthResponse {
  status: 'operational' | 'degraded' | 'offline';
  service: string;
  version: string;
  timestamp: string;
  uptime_seconds: number;
  system: {
    os: string;
    os_release: string;
    os_version: string;
    python: string;
    host: string;
    port: string;
  };
  subsystems: {
    database: SubsystemStatus;
    ai_provider: SubsystemStatus;
    security: SubsystemStatus;
    automation: SubsystemStatus;
  };
  capabilities: string[];
}

export type ConnectionState = 'connected' | 'connecting' | 'disconnected' | 'error';

