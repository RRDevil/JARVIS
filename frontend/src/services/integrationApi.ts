/**
 * API Service for Modular Application Integrations (Phase 5.2).
 */

import {
  ApplicationManifest,
  AppPermissionState,
  PermissionUpdatePayload,
  IntegrationActivityLogEntry,
} from '../types/integrations';

const BACKEND_URL = 'http://127.0.0.1:8000';
const BASE_ENDPOINT =
  window.location.port === '5173'
    ? '/api/v1/integrations'
    : `${BACKEND_URL}/api/v1/integrations`;

export async function fetchApplications(category?: string): Promise<ApplicationManifest[]> {
  const url = category ? `${BASE_ENDPOINT}/applications?category=${encodeURIComponent(category)}` : `${BASE_ENDPOINT}/applications`;
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`Failed to fetch applications: ${res.statusText}`);
  }
  return res.json();
}

export async function triggerAppDiscovery(refreshInstalled: boolean = true): Promise<ApplicationManifest[]> {
  const res = await fetch(`${BASE_ENDPOINT}/discover?refresh_installed=${refreshInstalled}`, {
    method: 'POST',
  });
  if (!res.ok) {
    throw new Error(`Failed to refresh discovery: ${res.statusText}`);
  }
  return res.json();
}

export async function fetchAppPermissions(appId: string): Promise<AppPermissionState> {
  const res = await fetch(`${BASE_ENDPOINT}/permissions/${encodeURIComponent(appId)}`);
  if (!res.ok) {
    throw new Error(`Failed to fetch permissions for ${appId}: ${res.statusText}`);
  }
  return res.json();
}

export async function updateAppPermissions(payload: PermissionUpdatePayload): Promise<AppPermissionState> {
  const res = await fetch(`${BASE_ENDPOINT}/permissions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    throw new Error(`Failed to update permissions for ${payload.app_id}: ${res.statusText}`);
  }
  return res.json();
}

export async function fetchIntegrationActivity(limit: number = 25): Promise<IntegrationActivityLogEntry[]> {
  const res = await fetch(`${BASE_ENDPOINT}/activity?limit=${limit}`);
  if (!res.ok) {
    throw new Error(`Failed to fetch integration activity: ${res.statusText}`);
  }
  const data = await res.json();
  return data.activity || [];
}
