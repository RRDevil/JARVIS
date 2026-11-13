import { HealthResponse } from '../types/health';
import {
  ApprovalRequest,
  ToolExecution,
  AuditEvent,
  MonitorInfo,
  ScreenInspectRequest,
  ScreenInspectResponse,
  OCRResult,
  VoiceInfo,
  VoiceStatusResponse,
  SpeechSynthesizeRequest,
  SpeechSynthesizeResponse,
  TranscriptionResponse,
  TTSProviderInfo,
  VoiceProfile,
  VoicePreviewRequest,
  VoicepackInfo,
  VoicepackImportResponse,
  ModelsStorageStatus,
  LocateElementsRequest,
  LocateElementsResponse,
  RecordingStartRequest,
  RecordingStatus,
  RecordingClipInfo,
} from '../types/contracts';

/**
 * Base API URL pointing to the FastAPI backend.
 * Falls back to direct 127.0.0.1:8000 if running standalone or via proxy.
 */
const BACKEND_URL = 'http://127.0.0.1:8000';

function getApiEndpoint(path: string): string {
  const cleanPath = path.startsWith('/') ? path : `/${path}`;
  if (typeof window !== 'undefined' && window.location.port === '5173') {
    return `/api${cleanPath}`;
  }
  return `${BACKEND_URL}/api${cleanPath}`;
}

export async function fetchHealthStatus(): Promise<{ data: HealthResponse; latencyMs: number }> {
  const startTime = performance.now();
  const endpoint = getApiEndpoint('/health');

  const response = await fetch(endpoint, {
    method: 'GET',
    headers: {
      Accept: 'application/json',
    },
  });

  const latencyMs = Math.round(performance.now() - startTime);

  if (!response.ok) {
    throw new Error(`Health check failed with status ${response.status}: ${response.statusText}`);
  }

  const data: HealthResponse = await response.json();
  return { data, latencyMs };
}

export async function fetchPendingApprovals(): Promise<ApprovalRequest[]> {
  const endpoint = getApiEndpoint('/v1/approvals/pending');
  const response = await fetch(endpoint, {
    method: 'GET',
    headers: { Accept: 'application/json' },
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch pending approvals: ${response.statusText}`);
  }

  return response.json();
}

export async function respondToApproval(
  approvalId: string,
  approved: boolean,
  expectedRequestId?: string
): Promise<{ approval: ApprovalRequest; execution?: ToolExecution; conversation_message?: string }> {
  const endpoint = getApiEndpoint(`/v1/approvals/${approvalId}/respond`);
  const response = await fetch(endpoint, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
    },
    body: JSON.stringify({ approved, expected_request_id: expectedRequestId || approvalId }),
  });

  if (!response.ok) {
    const errorJson = await response.json().catch(() => ({}));
    throw new Error(errorJson.detail || `Approval response failed: ${response.statusText}`);
  }

  return response.json();
}

export async function respondToActiveApproval(
  approved: boolean,
  expectedRequestId?: string
): Promise<{ approval: ApprovalRequest; execution?: ToolExecution; conversation_message?: string }> {
  const endpoint = getApiEndpoint('/v1/approvals/active/respond');
  const response = await fetch(endpoint, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
    },
    body: JSON.stringify({ approved, expected_request_id: expectedRequestId }),
  });

  if (!response.ok) {
    const errorJson = await response.json().catch(() => ({}));
    throw new Error(errorJson.detail || `Active approval response failed: ${response.statusText}`);
  }

  return response.json();
}

export async function proposeToolExecution(
  toolName: string,
  parameters: Record<string, any>
): Promise<{ execution: ToolExecution; approval_request?: ApprovalRequest }> {
  const endpoint = getApiEndpoint('/v1/tools/propose');
  const response = await fetch(endpoint, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
    },
    body: JSON.stringify({
      tool_name: toolName,
      parameters,
    }),
  });

  if (!response.ok) {
    const errorJson = await response.json().catch(() => ({}));
    throw new Error(errorJson.detail || `Tool proposal failed: ${response.statusText}`);
  }

  return response.json();
}

export async function fetchRecentAuditLogs(limit: number = 20): Promise<AuditEvent[]> {
  const endpoint = getApiEndpoint(`/v1/audit/logs?limit=${limit}`);
  const response = await fetch(endpoint, {
    method: 'GET',
    headers: { Accept: 'application/json' },
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch audit logs: ${response.statusText}`);
  }

  const rawLogs: Array<{
    id: number;
    timestamp: string;
    action_name: string;
    risk_tier: string;
    status: string;
    details: any;
  }> = await response.json();

  return rawLogs.map((log) => ({
    id: `audit-${log.id}`,
    timestamp: new Date(log.timestamp).toLocaleTimeString(),
    severity:
      log.risk_tier === 'CRITICAL'
        ? 'CRITICAL'
        : log.risk_tier === 'CONSEQUENTIAL'
        ? 'WARNING'
        : 'INFO',
    eventType: log.action_name,
    details: typeof log.details === 'string' ? log.details : JSON.stringify(log.details),
    isSimulated: false,
  }));
}

export async function shutdownSystem(): Promise<{ status: string; message: string }> {
  const endpoint = getApiEndpoint('/v1/system/shutdown');
  try {
    const response = await fetch(endpoint, {
      method: 'POST',
      headers: {
        Accept: 'application/json',
      },
    });
    if (!response.ok) {
      throw new Error(`Shutdown call failed: ${response.status}`);
    }
    return response.json();
  } catch (err: any) {
    // If backend socket closes abruptly because process terminated, treat as successful dispatch
    return { status: 'shutting_down', message: 'Shutdown signal delivered.' };
  }
}

export async function fetchMonitors(): Promise<MonitorInfo[]> {
  const endpoint = getApiEndpoint('/v1/screen/monitors');
  const response = await fetch(endpoint, {
    method: 'GET',
    headers: { Accept: 'application/json' },
  });
  if (!response.ok) {
    throw new Error(`Failed to query display monitors: ${response.statusText}`);
  }
  return response.json();
}

export async function inspectScreen(req: ScreenInspectRequest): Promise<ScreenInspectResponse> {
  const endpoint = getApiEndpoint('/v1/screen/inspect');
  const response = await fetch(endpoint, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
    },
    body: JSON.stringify(req),
  });
  if (!response.ok) {
    const errorJson = await response.json().catch(() => ({}));
    throw new Error(errorJson.detail || `Screen inspection failed: ${response.statusText}`);
  }
  return response.json();
}

export async function runScreenOcr(req: ScreenInspectRequest = {}): Promise<OCRResult> {
  const endpoint = getApiEndpoint('/v1/screen/ocr');
  const response = await fetch(endpoint, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
    },
    body: JSON.stringify(req),
  });
  if (!response.ok) {
    const errorJson = await response.json().catch(() => ({}));
    throw new Error(errorJson.detail || `Screen OCR failed: ${response.statusText}`);
  }
  return response.json();
}

export async function fetchVoiceStatus(): Promise<VoiceStatusResponse> {
  const endpoint = getApiEndpoint('/v1/voice/status');
  const response = await fetch(endpoint, {
    method: 'GET',
    headers: { Accept: 'application/json' },
  });
  if (!response.ok) {
    throw new Error(`Failed to fetch voice status: ${response.statusText}`);
  }
  return response.json();
}

export async function fetchVoiceList(): Promise<{ voices: VoiceInfo[]; default_voice_id: string }> {
  const endpoint = getApiEndpoint('/v1/voice/voices');
  const response = await fetch(endpoint, {
    method: 'GET',
    headers: { Accept: 'application/json' },
  });
  if (!response.ok) {
    throw new Error(`Failed to fetch voice list: ${response.statusText}`);
  }
  return response.json();
}

export async function synthesizeSpeech(req: SpeechSynthesizeRequest): Promise<SpeechSynthesizeResponse> {
  const endpoint = getApiEndpoint('/v1/voice/synthesize');
  const response = await fetch(endpoint, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
    },
    body: JSON.stringify(req),
  });
  if (!response.ok) {
    const errorJson = await response.json().catch(() => ({}));
    throw new Error(errorJson.detail || `Speech synthesis failed: ${response.statusText}`);
  }
  return response.json();
}

export async function transcribeAudio(audioBlob: Blob): Promise<TranscriptionResponse> {
  const endpoint = getApiEndpoint('/v1/voice/transcribe');
  const formData = new FormData();
  let ext = 'webm';
  if (audioBlob.type) {
    if (audioBlob.type.includes('wav')) {
      ext = 'wav';
    } else if (audioBlob.type.includes('ogg')) {
      ext = 'ogg';
    } else if (audioBlob.type.includes('mp4') || audioBlob.type.includes('m4a')) {
      ext = 'm4a';
    }
  }
  formData.append('file', audioBlob, `microphone_input.${ext}`);

  const response = await fetch(endpoint, {
    method: 'POST',
    headers: {
      Accept: 'application/json',
    },
    body: formData,
  });
  if (!response.ok) {
    const errorJson = await response.json().catch(() => ({}));
    throw new Error(errorJson.detail || `Audio transcription failed: ${response.statusText}`);
  }
  return response.json();
}

export async function setSTTModel(modelSize: string): Promise<{ status: string; model_size: string }> {
  const endpoint = getApiEndpoint('/v1/voice/stt-model');
  const response = await fetch(endpoint, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
    },
    body: JSON.stringify({ model_size: modelSize }),
  });
  if (!response.ok) {
    const errorJson = await response.json().catch(() => ({}));
    throw new Error(errorJson.detail || `Failed to switch STT model: ${response.statusText}`);
  }
  return response.json();
}

export async function fetchTTSProviders(): Promise<TTSProviderInfo[]> {
  const endpoint = getApiEndpoint('/v1/voice/providers');
  const response = await fetch(endpoint, {
    method: 'GET',
    headers: { Accept: 'application/json' },
  });
  if (!response.ok) {
    throw new Error(`Failed to fetch TTS providers: ${response.statusText}`);
  }
  return response.json();
}

export async function fetchVoiceProfiles(): Promise<VoiceProfile[]> {
  const endpoint = getApiEndpoint('/v1/voice/profiles');
  const response = await fetch(endpoint, {
    method: 'GET',
    headers: { Accept: 'application/json' },
  });
  if (!response.ok) {
    throw new Error(`Failed to fetch voice profiles: ${response.statusText}`);
  }
  return response.json();
}

export async function fetchActiveVoiceProfile(): Promise<VoiceProfile> {
  const endpoint = getApiEndpoint('/v1/voice/profiles/active');
  const response = await fetch(endpoint, {
    method: 'GET',
    headers: { Accept: 'application/json' },
  });
  if (!response.ok) {
    throw new Error(`Failed to fetch active voice profile: ${response.statusText}`);
  }
  return response.json();
}

export async function setActiveVoiceProfile(profileId: string): Promise<VoiceProfile> {
  const endpoint = getApiEndpoint('/v1/voice/profiles/active');
  const response = await fetch(endpoint, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
    },
    body: JSON.stringify({ profile_id: profileId }),
  });
  if (!response.ok) {
    const errorJson = await response.json().catch(() => ({}));
    throw new Error(errorJson.detail || `Failed to set active voice profile: ${response.statusText}`);
  }
  return response.json();
}

export async function createVoiceProfile(profile: Partial<VoiceProfile>): Promise<VoiceProfile> {
  const endpoint = getApiEndpoint('/v1/voice/profiles');
  const response = await fetch(endpoint, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
    },
    body: JSON.stringify(profile),
  });
  if (!response.ok) {
    const errorJson = await response.json().catch(() => ({}));
    throw new Error(errorJson.detail || `Failed to create voice profile: ${response.statusText}`);
  }
  return response.json();
}

export async function updateVoiceProfile(profileId: string, updates: Partial<VoiceProfile>): Promise<VoiceProfile> {
  const endpoint = getApiEndpoint(`/v1/voice/profiles/${profileId}`);
  const response = await fetch(endpoint, {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
    },
    body: JSON.stringify(updates),
  });
  if (!response.ok) {
    const errorJson = await response.json().catch(() => ({}));
    throw new Error(errorJson.detail || `Failed to update voice profile: ${response.statusText}`);
  }
  return response.json();
}

export async function deleteVoiceProfile(profileId: string): Promise<void> {
  const endpoint = getApiEndpoint(`/v1/voice/profiles/${profileId}`);
  const response = await fetch(endpoint, {
    method: 'DELETE',
    headers: { Accept: 'application/json' },
  });
  if (!response.ok) {
    const errorJson = await response.json().catch(() => ({}));
    throw new Error(errorJson.detail || `Failed to delete voice profile: ${response.statusText}`);
  }
}

export async function generateVoicePreview(req: VoicePreviewRequest): Promise<SpeechSynthesizeResponse> {
  const endpoint = getApiEndpoint('/v1/voice/preview');
  const response = await fetch(endpoint, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
    },
    body: JSON.stringify(req),
  });
  if (!response.ok) {
    const errorJson = await response.json().catch(() => ({}));
    throw new Error(errorJson.detail || `Failed to generate voice preview: ${response.statusText}`);
  }
  return response.json();
}

export async function fetchVoicepacks(): Promise<VoicepackInfo[]> {
  const endpoint = getApiEndpoint('/v1/voice/voicepacks');
  const response = await fetch(endpoint, {
    method: 'GET',
    headers: { Accept: 'application/json' },
  });
  if (!response.ok) {
    throw new Error(`Failed to fetch voicepacks: ${response.statusText}`);
  }
  return response.json();
}

export async function importVoicepack(file: File): Promise<VoicepackImportResponse> {
  const endpoint = getApiEndpoint('/v1/voice/voicepacks/import');
  const formData = new FormData();
  formData.append('file', file);

  const response = await fetch(endpoint, {
    method: 'POST',
    headers: { Accept: 'application/json' },
    body: formData,
  });
  if (!response.ok) {
    const errorJson = await response.json().catch(() => ({}));
    throw new Error(errorJson.detail || `Voicepack import failed: ${response.statusText}`);
  }
  return response.json();
}

export async function deleteVoicepack(voicepackId: string): Promise<{ status: string; message: string }> {
  const endpoint = getApiEndpoint(`/v1/voice/voicepacks/${encodeURIComponent(voicepackId)}`);
  const response = await fetch(endpoint, {
    method: 'DELETE',
    headers: { Accept: 'application/json' },
  });
  if (!response.ok) {
    const errorJson = await response.json().catch(() => ({}));
    throw new Error(errorJson.detail || `Failed to delete voicepack: ${response.statusText}`);
  }
  return response.json();
}

export async function fetchModelsStorageStatus(): Promise<ModelsStorageStatus> {
  const endpoint = getApiEndpoint('/v1/voice/models/status');
  const response = await fetch(endpoint, {
    method: 'GET',
    headers: { Accept: 'application/json' },
  });
  if (!response.ok) {
    throw new Error(`Failed to fetch models storage status: ${response.statusText}`);
  }
  return response.json();
}

export async function configureModelsPath(path: string): Promise<ModelsStorageStatus> {
  const endpoint = getApiEndpoint('/v1/voice/models/configure-path');
  const response = await fetch(endpoint, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
    },
    body: JSON.stringify({ path }),
  });
  if (!response.ok) {
    const errorJson = await response.json().catch(() => ({}));
    throw new Error(errorJson.detail || `Failed to configure models path: ${response.statusText}`);
  }
  return response.json();
}

export async function importModelFromPath(sourcePath: string, targetName?: string): Promise<VoicepackImportResponse> {
  const endpoint = getApiEndpoint('/v1/voice/models/import-path');
  const response = await fetch(endpoint, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
    },
    body: JSON.stringify({ source_path: sourcePath, target_name: targetName }),
  });
  if (!response.ok) {
    const errorJson = await response.json().catch(() => ({}));
    throw new Error(errorJson.detail || `Model import failed: ${response.statusText}`);
  }
  return response.json();
}

// --- Phase 5: Visual UI Element Grounding & Recording API ---

export async function locateScreenElements(req: LocateElementsRequest = {}): Promise<LocateElementsResponse> {
  const endpoint = getApiEndpoint('/v1/screen/elements/locate');
  const response = await fetch(endpoint, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
    },
    body: JSON.stringify(req),
  });
  if (!response.ok) {
    const errorJson = await response.json().catch(() => ({}));
    throw new Error(errorJson.detail || `Element localization failed: ${response.statusText}`);
  }
  return response.json();
}

export async function startScreenRecording(req: RecordingStartRequest = {}): Promise<RecordingStatus> {
  const endpoint = getApiEndpoint('/v1/screen/record/start');
  const response = await fetch(endpoint, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
    },
    body: JSON.stringify(req),
  });
  if (!response.ok) {
    const errorJson = await response.json().catch(() => ({}));
    throw new Error(errorJson.detail || `Start recording failed: ${response.statusText}`);
  }
  return response.json();
}

export async function stopScreenRecording(): Promise<RecordingClipInfo | null> {
  const endpoint = getApiEndpoint('/v1/screen/record/stop');
  const response = await fetch(endpoint, {
    method: 'POST',
    headers: { Accept: 'application/json' },
  });
  if (!response.ok) {
    const errorJson = await response.json().catch(() => ({}));
    throw new Error(errorJson.detail || `Stop recording failed: ${response.statusText}`);
  }
  return response.json();
}

export async function fetchScreenRecordingStatus(): Promise<RecordingStatus> {
  const endpoint = getApiEndpoint('/v1/screen/record/status');
  const response = await fetch(endpoint, {
    method: 'GET',
    headers: { Accept: 'application/json' },
  });
  if (!response.ok) {
    throw new Error(`Failed to query recording status: ${response.statusText}`);
  }
  return response.json();
}

export async function fetchScreenRecordingClips(): Promise<RecordingClipInfo[]> {
  const endpoint = getApiEndpoint('/v1/screen/record/clips');
  const response = await fetch(endpoint, {
    method: 'GET',
    headers: { Accept: 'application/json' },
  });
  if (!response.ok) {
    throw new Error(`Failed to list recording clips: ${response.statusText}`);
  }
  return response.json();
}



