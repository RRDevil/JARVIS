/**
 * Modular Application Integration Framework Types (Phase 5.2).
 */

export type AppCategory = 'browser' | 'office' | 'messaging' | 'development' | 'utility' | 'system';

export type ProviderType = 'desktop_ui' | 'office_com' | 'browser_automation' | 'native_api';

export type PermissionLevel = 'read_only' | 'controlled' | 'consequential' | 'restricted';

export type IntegrationHealth = 'healthy' | 'degraded' | 'unavailable' | 'not_installed' | 'unknown';

export interface CapabilitySpec {
  id: string;
  name: string;
  description: string;
  permission_level: PermissionLevel;
  risk_tier: 'READ_ONLY' | 'LOW_RISK' | 'HIGH_RISK' | 'CRITICAL';
  supported_providers: ProviderType[];
  parameters_schema?: Record<string, any>;
}

export interface ProcessRule {
  executable_names: string[];
  window_title_patterns: string[];
  window_class_names?: string[];
  registry_app_paths_keys: string[];
  common_install_paths: string[];
}

export interface ApplicationManifest {
  app_id: string;
  display_name: string;
  vendor: string;
  category: AppCategory;
  description: string;
  process_rule: ProcessRule;
  supported_providers: ProviderType[];
  capabilities: CapabilitySpec[];
  is_enabled: boolean;
  is_installed: boolean;
  installed_path?: string | null;
  is_running: boolean;
  running_pids: number[];
  running_window_handles: number[];
  health_status: IntegrationHealth;
  version?: string | null;
  metadata?: Record<string, any>;
}

export interface AppPermissionState {
  app_id: string;
  is_enabled: boolean;
  disabled_providers: ProviderType[];
  disabled_capabilities: string[];
  require_approval_overrides: Record<string, boolean>;
}

export interface PermissionUpdatePayload {
  app_id: string;
  is_enabled?: boolean;
  disabled_providers?: string[];
  disabled_capabilities?: string[];
}

export interface IntegrationActivityLogEntry {
  timestamp: string;
  app_id: string;
  capability_id: string;
  provider: ProviderType;
  success: boolean;
  summary: string;
  error?: string | null;
}
