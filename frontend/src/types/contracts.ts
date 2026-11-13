/**
 * Integration Contracts for Future JARVIS Capabilities.
 *
 * Defines the typed interface specifications for:
 * - Conversation & Streaming Assistant Messages (Phase 2)
 * - Tool Execution & Consequential Action Approvals (Phase 3)
 * - Task Planning & Multi-step Workflows (Phase 6)
 * - Security & Audit Logging (Phase 7)
 */

export type MessageRole = 'user' | 'assistant' | 'system';
export type MessageStatus = 'streaming' | 'completed' | 'error';

export interface ChatMessage {
  id: string;
  role: MessageRole;
  content: string;
  timestamp: string;
  numericTimestamp?: number;
  status: MessageStatus;
  tokenCount?: number;
  model?: string;
  approvalRequest?: ApprovalRequest;
  fadingOut?: boolean;
  imagePreview?: string;
  ocrSummary?: string;
}

export interface MonitorInfo {
  monitor_id: number;
  name: string;
  left: number;
  top: number;
  width: number;
  height: number;
  is_primary: boolean;
}

export interface BoundingBox {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface OCRWord {
  text: string;
  bounding_box: BoundingBox;
  confidence: number;
}

export interface OCRLine {
  text: string;
  words: OCRWord[];
}

export interface OCRResult {
  full_text: string;
  lines: OCRLine[];
  line_count: number;
  word_count: number;
  confidence: number;
  duration_ms: number;
}

export interface CapturedScreen {
  monitor_id: number;
  width: number;
  height: number;
  captured_at: string;
  active_window_title?: string;
  image_base64?: string;
  ocr_result?: OCRResult;
}

export type PerceptionStage =
  | 'IDLE'
  | 'CAPTURING'
  | 'READING_OCR'
  | 'ANALYZING_VISION'
  | 'GENERATING'
  | 'COMPLETED'
  | 'FAILED'
  | 'CANCELLED';

export interface PerceptionProgress {
  requestId: string | null;
  stage: PerceptionStage;
  stageMessage: string;
  targetDescription: string;
  mode: 'ocr_only' | 'gemini_vision' | null;
  startTime: number | null;
  elapsedMs: number;
  error?: string | null;
}

export interface ScreenInspectRequest {
  request_id?: string;
  monitor_id?: number;
  active_window_only?: boolean;
  include_ocr?: boolean;
  authorize_gemini_vision?: boolean;
}

export interface ScreenInspectResponse {
  request_id?: string;
  screen: CapturedScreen;
  gemini_vision_authorized: boolean;
  message: string;
  capture_duration_ms?: number;
  ocr_duration_ms?: number;
  stage?: string;
}

export type RiskTier = 'READ_ONLY' | 'CONTROLLED' | 'CONSEQUENTIAL' | 'CRITICAL';
export type ToolStatus = 'proposed' | 'pending_approval' | 'approved' | 'rejected' | 'running' | 'success' | 'failed';

export interface ToolExecution {
  id: string;
  toolName: string;
  riskTier: RiskTier;
  parameters: Record<string, any>;
  status: ToolStatus;
  requestedAt: string;
  completedAt?: string;
  result?: any;
  error?: string;
}

export interface ApprovalRequest {
  id: string;
  toolExecutionId: string;
  actionSummary: string;
  toolName: string;
  riskTier: RiskTier;
  parameters: Record<string, any>;
  requestedAt: string;
  expiresAt: string;
  status: 'pending' | 'approved' | 'rejected';
}

export type TaskStatus = 'planning' | 'in_progress' | 'awaiting_approval' | 'completed' | 'cancelled';

export interface TaskStep {
  index: number;
  description: string;
  toolName?: string;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'skipped';
}

export interface TaskPlan {
  id: string;
  goal: string;
  status: TaskStatus;
  steps: TaskStep[];
  currentStepIndex: number;
  createdAt: string;
}

export type AuditSeverity = 'INFO' | 'WARNING' | 'CRITICAL' | 'SECURITY';

export interface AuditEvent {
  id: string;
  timestamp: string;
  severity: AuditSeverity;
  eventType: string;
  details: string;
  isSimulated?: boolean; // Clearly tags demo/mock preview events
}

export type TTSProviderStatus = 'installed_ready' | 'not_installed' | 'initializing' | 'unavailable' | 'error';

export type VoicepackStatus = 'installed' | 'not_installed' | 'corrupted';

export interface VoicepackInfo {
  id: string;
  name: string;
  provider_id: string;
  language: string;
  model_path: string;
  config_path: string;
  sample_rate: number;
  num_speakers: number;
  speakers: string[];
  size_bytes: number;
  status: VoicepackStatus;
  license?: string | null;
  attribution?: string | null;
  description?: string | null;
  is_builtin?: boolean;
}

export interface VoicepackImportResponse {
  success: boolean;
  message: string;
  voicepack?: VoicepackInfo | null;
  profile_created?: VoiceProfile | null;
}

export interface TTSProviderInfo {
  id: string;
  name: string;
  status: TTSProviderStatus;
  description: string;
  is_local: boolean;
  supports_custom_voices: boolean;
  supports_pitch: boolean;
  supports_emotions: boolean;
  error_message?: string | null;
  voice_count: number;
}

export interface VoiceProfile {
  id: string;
  name: string;
  provider_id: string;
  voice_id: string;
  language: string;
  rate: number;
  pitch?: number | null;
  volume: number;
  style?: string | null;
  is_favorite: boolean;
  is_default: boolean;
  is_fallback: boolean;
  metadata?: Record<string, any>;
}

export interface VoicePreviewRequest {
  profile_id?: string;
  provider_id?: string;
  voice_id?: string;
  text?: string;
  rate?: number;
  pitch?: number;
  volume?: number;
}

export interface VoiceInfo {
  id: string;
  name: string;
  provider_id?: string;
  provider_name?: string;
  gender?: string | null;
  languages: string[];
  styles?: string[];
  is_default: boolean;
}

export interface SpeechSynthesizeRequest {
  text: string;
  profile_id?: string;
  voice_id?: string;
  provider_id?: string;
  rate?: number;
  pitch?: number;
  volume?: number;
  format?: string;
  delivery_profile?: string;
  noise_scale?: number;
  noise_w_scale?: number;
  length_scale?: number;
  metadata?: Record<string, any>;
}

export interface SpeechSynthesizeResponse {
  audio_base64: string;
  mime_type: string;
  duration_seconds?: number;
  voice_used: string;
  provider_used?: string;
  fallback_applied?: boolean;
  fallback_reason?: string | null;
}

export interface TranscriptionResponse {
  text: string;
  confidence: number;
  language: string;
  duration_seconds: number;
  provider: string;
}

export interface VoiceStatusResponse {
  stt_available: boolean;
  tts_available: boolean;
  stt_provider: string;
  tts_provider: string;
  stt_model_loaded: boolean;
  stt_model_size?: string;
  available_stt_models?: string[];
  available_voices: VoiceInfo[];
  active_profile_id?: string;
  active_profile_name?: string;
  active_provider_id?: string;
  providers?: TTSProviderInfo[];
}

export interface ModelsStorageStatus {
  active_models_dir: string;
  is_external: boolean;
  total_size_mb: number;
  stt_models_count: number;
  tts_voicepacks_count: number;
  rvc_models_count: number;
  scan_directories: string[];
}

// --- Phase 5: Grounded Visual UI Interaction & Recording Contracts ---

export type ElementType =
  | 'button'
  | 'text_field'
  | 'search_bar'
  | 'checkbox'
  | 'radio_button'
  | 'menu'
  | 'tab'
  | 'icon'
  | 'link'
  | 'combobox'
  | 'list_item'
  | 'window_control'
  | 'generic_clickable';

export type ElementSource = 'uia' | 'ocr' | 'vision' | 'hybrid';

export interface ElementBoundingBox {
  left: number;
  top: number;
  width: number;
  height: number;
}

export interface PointCoordinate {
  x: number;
  y: number;
}

export interface GroundedUIElement {
  element_id: string;
  description: string;
  text: string;
  element_type: ElementType;
  bounding_box: ElementBoundingBox;
  center: PointCoordinate;
  confidence: number;
  is_interactable: boolean;
  source: ElementSource;
  timestamp: string;
  window_title?: string | null;
  window_handle?: number | null;
}

export interface LocateElementsRequest {
  query?: string;
  monitor_id?: number;
  active_window_only?: boolean;
  element_type?: ElementType;
  max_results?: number;
}

export interface LocateElementsResponse {
  elements: GroundedUIElement[];
  total_found: number;
  active_window?: string | null;
  screen_width: number;
  screen_height: number;
  observation_timestamp: string;
  is_stale: boolean;
}

export type GroundedActionType = 'click' | 'double_click' | 'right_click' | 'type_text' | 'scroll';

export interface GroundedInteractionRequest {
  target_description?: string;
  element_id?: string;
  action?: GroundedActionType;
  text_to_type?: string;
  scroll_direction?: 'up' | 'down';
  scroll_amount?: number;
  active_window_only?: boolean;
  monitor_id?: number;
  verify_post_condition?: boolean;
}

export interface GroundedInteractionResponse {
  success: boolean;
  action: GroundedActionType;
  target_element?: GroundedUIElement | null;
  message: string;
  verified: boolean;
  requires_approval: boolean;
  approval_id?: string | null;
  execution_time_ms: number;
}

export interface RecordingStartRequest {
  duration_seconds?: number;
  fps?: number;
  monitor_id?: number;
  active_window_only?: boolean;
}

export interface RecordingStatus {
  is_recording: boolean;
  clip_id?: string | null;
  elapsed_seconds: number;
  max_duration_seconds: number;
  fps: number;
  frames_captured: number;
  file_path?: string | null;
}

export interface RecordingClipInfo {
  clip_id: string;
  created_at: string;
  duration_seconds: number;
  file_size_bytes: number;
  file_path: string;
  format: string;
  preview_base64?: string | null;
}


