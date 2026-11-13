import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { HealthResponse, ConnectionState } from './types/health';
import { AssistantState } from './types/assistantState';
import {
  UserSettings,
  DEFAULT_SETTINGS,
  DEFAULT_KEYBINDS,
  THEME_PALETTES,
  loadSettings,
  saveSettings,
  PanelId,
} from './types/settings';
import { AuditEvent, ChatMessage, ApprovalRequest, PerceptionProgress } from './types/contracts';
import {
  fetchHealthStatus,
  shutdownSystem,
  fetchPendingApprovals,
  respondToApproval,
  inspectScreen,
  transcribeAudio,
} from './services/api';
import { streamChatCompletion, ChatMessagePayload } from './services/chatStream';
import { soundManager } from './services/soundManager';
import { voicePlayer, audioRecorder } from './services/voiceService';
import { streamingVoice } from './services/streamingVoice';
import { speechQueue } from './services/speechQueue';
import { taskNarration } from './services/taskNarration';

import { TopStatusBar } from './components/TopStatusBar';
import { ArcReactor } from './components/ArcReactor';
import { PanelContainer } from './components/PanelContainer';
import { DiagnosticsPanel } from './components/DiagnosticsPanel';
import { SystemMetrics } from './components/SystemMetrics';
import { ActivityLogPanel } from './components/ActivityLogPanel';
import { ConversationPanel } from './components/ConversationPanel';
import { ApprovalPreviewPanel } from './components/ApprovalPreviewPanel';
import { DevStateSimulator } from './components/DevStateSimulator';
import { SettingsModal } from './components/SettingsModal';
import { QuickCommandBar } from './components/QuickCommandBar';
import { ApprovalBubble } from './components/ApprovalBubble';
import { ScreenPerceptionModal } from './components/ScreenPerceptionModal';
import { ApplicationManagerModal } from './components/ApplicationManagerModal';

import './styles/hud.css';

export type ViewMode = 'compact' | 'quick_input' | 'expanded' | 'dashboard';

/**
 * Validates whether a KeyboardEvent matches a user-defined shortcut string
 * (e.g. "Ctrl+Space", "Alt+Space", "Ctrl+Shift+S", "Escape", "F4", "ScrollLock").
 */
function matchesKeybind(e: KeyboardEvent, comboStr: string): boolean {
  if (!comboStr) return false;
  const parts = comboStr.split('+').map((p) => p.trim().toLowerCase());
  const hasCtrl = parts.includes('ctrl') || parts.includes('control');
  const hasAlt = parts.includes('alt');
  const hasShift = parts.includes('shift');
  const hasWin = parts.includes('win') || parts.includes('meta');

  if (e.ctrlKey !== hasCtrl) return false;
  if (e.altKey !== hasAlt) return false;
  if (e.shiftKey !== hasShift) return false;
  if (e.metaKey !== hasWin) return false;

  const mainKeys = parts.filter(
    (p) => !['ctrl', 'control', 'alt', 'shift', 'win', 'meta'].includes(p)
  );
  if (mainKeys.length === 0) return false;
  const target = mainKeys[0];

  const eventKey = e.key.toLowerCase();
  const eventCode = e.code.toLowerCase();

  if (target === 'space') {
    return eventKey === ' ' || eventCode === 'space';
  }
  if (target === 'escape' || target === 'esc') {
    return eventKey === 'escape';
  }
  if (target === 'scrolllock' || target === 'scroll lock') {
    return eventCode === 'scrolllock' || eventKey === 'scrolllock';
  }
  if (target === 'pause' || target === 'break') {
    return eventCode === 'pause' || eventKey === 'pause';
  }
  if (target === 'f20') {
    return eventKey === 'f20';
  }

  return (
    eventKey === target ||
    eventCode === `key${target}` ||
    eventCode === `digit${target}` ||
    eventCode === target
  );
}

export const App: React.FC = () => {
  // Desktop View Mode (Compact Orb by default, expandable to Glass HUD or Full Dashboard)
  const [viewMode, setViewMode] = useState<ViewMode>('compact');

  // Settings & Theme Customization
  const [settings, setSettings] = useState<UserSettings>(loadSettings);
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [isAppManagerOpen, setIsAppManagerOpen] = useState(false);

  // Assistant & Connection State
  const [assistantState, setAssistantState] = useState<AssistantState>('IDLE');
  const [connectionState, setConnectionState] = useState<ConnectionState>('connecting');
  const [healthData, setHealthData] = useState<HealthResponse | null>(null);
  const [latencyMs, setLatencyMs] = useState<number | null>(null);
  const [lastChecked, setLastChecked] = useState<string>('');
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isShuttingDown, setIsShuttingDown] = useState(false);

  // Shared Unified Conversation State across all modes
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: 'welcome-0',
      role: 'assistant',
      content:
        'Good day, Sir. J.A.R.V.I.S. neural interface is active and linked. ' +
        'How may I assist you with your desktop operations today?',
      timestamp: new Date().toLocaleTimeString(),
      status: 'completed',
      model: 'J.A.R.V.I.S. Core',
    },
  ]);
  const [isStreaming, setIsStreaming] = useState(false);
  const isStreamingRef = React.useRef(false);
  useEffect(() => {
    isStreamingRef.current = isStreaming;
  }, [isStreaming]);
  const [pendingApprovals, setPendingApprovals] = useState<ApprovalRequest[]>([]);
  const pendingApprovalsRef = React.useRef<ApprovalRequest[]>([]);
  useEffect(() => {
    pendingApprovalsRef.current = pendingApprovals;
  }, [pendingApprovals]);
  const [isPerceptionModalOpen, setIsPerceptionModalOpen] = useState(false);
  const [isPerceiving, setIsPerceiving] = useState(false);
  const [perceptionProgress, setPerceptionProgress] = useState<PerceptionProgress>({
    requestId: null,
    stage: 'IDLE',
    stageMessage: '',
    targetDescription: '',
    mode: null,
    startTime: null,
    elapsedMs: 0,
    error: null,
  });
  const abortControllerRef = React.useRef<AbortController | null>(null);
  const activePerceptionReqIdRef = React.useRef<string | null>(null);
  const perceptionAbortControllerRef = React.useRef<AbortController | null>(null);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [isTranscribing, setIsTranscribing] = useState(false);

  // Complete Shutdown / Process Termination Handler
  const handleCompleteShutdown = useCallback(async () => {
    const confirmed = window.confirm(
      'Completely shut down J.A.R.V.I.S.?\nThis will terminate the application, stop the server, and release all system ports.'
    );
    if (!confirmed) return;

    setIsShuttingDown(true);
    soundManager.play('DEACTIVATION');

    try {
      if ((window as any).pywebview?.api?.exit_app) {
        (window as any).pywebview.api.exit_app();
      }
      await shutdownSystem();
    } catch {
      // Termination signal handled
    }
  }, []);

  // Activity Events Log
  const [activityEvents, setActivityEvents] = useState<AuditEvent[]>([
    {
      id: 'init-0',
      timestamp: new Date().toLocaleTimeString(),
      severity: 'INFO',
      eventType: 'SYSTEM_BOOT',
      details: 'JARVIS Native Desktop Presentation Engine initialized.',
      isSimulated: false,
    },
  ]);

  // Window mode synchronization with native desktop shell
  const changeViewMode = useCallback((mode: ViewMode) => {
    setViewMode(mode);
    soundManager.play('ACTIVATION');
    if ((window as any).pywebview?.api?.set_mode) {
      (window as any).pywebview.api.set_mode(mode);
    }
  }, []);

  // External shell mode synchronization (e.g. from System Tray)
  useEffect(() => {
    const handleExternalMode = (e: Event) => {
      const mode = (e as CustomEvent).detail;
      if (mode === 'compact' || mode === 'quick_input' || mode === 'expanded' || mode === 'dashboard') {
        setViewMode(mode);
        soundManager.play('ACTIVATION');
      }
    };
    window.addEventListener('jarvis:set_mode', handleExternalMode);
    return () => window.removeEventListener('jarvis:set_mode', handleExternalMode);
  }, []);

  // Sync settings with Sound Manager and CSS Custom Properties
  useEffect(() => {
    soundManager.setEnabled(settings.soundEnabled);
    soundManager.setVolume(settings.soundVolume);

    const palette = THEME_PALETTES[settings.theme] || THEME_PALETTES.cyan;
    const root = document.documentElement;
    root.style.setProperty('--hud-primary', palette.primary);
    root.style.setProperty('--hud-glow', palette.glow);
    root.style.setProperty('--hud-dim', palette.dim);
    root.style.setProperty(
      '--hud-panel-bg',
      `rgba(6, 18, 38, ${settings.panelOpacity})`
    );

    saveSettings(settings);
  }, [settings]);

  // Health Polling (every 3.5 seconds)
  const pollHealth = useCallback(async () => {
    try {
      const { data, latencyMs } = await fetchHealthStatus();
      setHealthData(data);
      setLatencyMs(latencyMs);
      setConnectionState('connected');
      setErrorMessage(null);
      setLastChecked(new Date().toLocaleTimeString());
    } catch (err: any) {
      setConnectionState('disconnected');
      setErrorMessage(err.message || 'Unable to connect to JARVIS Core backend.');
      setLatencyMs(null);
    }
  }, []);

  useEffect(() => {
    pollHealth();
    const interval = setInterval(pollHealth, 3500);
    return () => clearInterval(interval);
  }, [pollHealth]);

  // Continuous Approval Polling (every 2.5 seconds) across ALL modes
  const knownPendingApprovalsRef = React.useRef<Map<string, string>>(new Map());
  const announcedExpiredApprovalsRef = React.useRef<Set<string>>(new Set());

  const pollApprovals = useCallback(async () => {
    try {
      const list = await fetchPendingApprovals();
      const now = Date.now();

      // Check previously known approvals that have expired
      for (const [id, expiresAtStr] of knownPendingApprovalsRef.current.entries()) {
        const isStillPending = list.some((r) => r.id === id);
        const hasTimeExpired = Date.parse(expiresAtStr) <= now;
        if (!isStillPending && hasTimeExpired && !announcedExpiredApprovalsRef.current.has(id)) {
          announcedExpiredApprovalsRef.current.add(id);
          setMessages((prev) => [
            ...prev,
            {
              id: `msg-expired-${id}-${now}`,
              role: 'assistant',
              content: "The approval request expired before it was authorized. I haven't performed the action.",
              timestamp: new Date().toLocaleTimeString(),
              numericTimestamp: now,
              status: 'completed',
              model: 'J.A.R.V.I.S. Core',
            },
          ]);
        }
      }

      // Spoken notification for newly registered approval requests
      for (const req of list) {
        if (!knownPendingApprovalsRef.current.has(req.id)) {
          taskNarration.announceApprovalRequired(req.actionSummary || 'Action', req.id, settings.voice);
        }
      }

      const nextMap = new Map<string, string>();
      for (const req of list) {
        nextMap.set(req.id, req.expiresAt);
      }
      knownPendingApprovalsRef.current = nextMap;

      setPendingApprovals(list);
      if (list.length > 0) {
        setAssistantState((prev) => (prev !== 'AWAITING_APPROVAL' ? 'AWAITING_APPROVAL' : prev));
      } else {
        setAssistantState((prev) => (prev === 'AWAITING_APPROVAL' ? 'IDLE' : prev));
      }
    } catch {
      // Backend polling failure handled gracefully
    }
  }, []);

  useEffect(() => {
    pollApprovals();
    const interval = setInterval(pollApprovals, 2500);
    return () => clearInterval(interval);
  }, [pollApprovals]);

  // Update Activity Log on significant events
  const logActivity = useCallback(
    (eventType: string, details: string, severity: AuditEvent['severity'] = 'INFO', isSimulated = false) => {
      setActivityEvents((prev) => [
        {
          id: `act-${Date.now()}-${Math.random().toString(36).substr(2, 4)}`,
          timestamp: new Date().toLocaleTimeString(),
          severity,
          eventType,
          details,
          isSimulated,
        },
        ...prev.slice(0, 40),
      ]);
    },
    []
  );

  // State Change Handler with Event Logging
  const handleStateChange = useCallback(
    (newState: AssistantState) => {
      setAssistantState(newState);
      logActivity(
        'STATE_TRANSITION',
        `Assistant state shifted to ${newState}`,
        newState === 'ERROR' ? 'CRITICAL' : newState === 'AWAITING_APPROVAL' ? 'WARNING' : 'INFO',
        true
      );
    },
    [logActivity]
  );

  // Prioritized Speech Queue Synchronization
  useEffect(() => {
    speechQueue.setCallbacks({
      onPlaybackStart: () => {
        setIsSpeaking(true);
      },
      onPlaybackComplete: () => {
        setIsSpeaking(false);
        setAssistantState((prev) => {
          if (pendingApprovalsRef.current.length > 0) return 'AWAITING_APPROVAL';
          if (isStreamingRef.current) {
            return prev === 'SPEAKING' ? 'EXECUTING' : prev;
          }
          return prev === 'SPEAKING' ? 'IDLE' : prev;
        });
      },
      onError: (err) => {
        setIsSpeaking(false);
        logActivity('VOICE_ERROR', `Speech queue error: ${err?.message || err}`, 'WARNING');
      },
    });
  }, [logActivity]);

  // Instant Speech Interruption Handler
  const handleStopSpeaking = useCallback(() => {
    voicePlayer.stop();
    streamingVoice.stop();
    speechQueue.stopAll();
    setIsSpeaking(false);
    setAssistantState((prev) => (prev === 'SPEAKING' || (prev === 'THINKING' && !isStreaming) ? 'IDLE' : prev));
    logActivity('VOICE_STOPPED', 'Voice output halted by operator.', 'INFO');
  }, [logActivity, isStreaming]);

  // Spoken Audio Synthesis Handler
  const handleSpeakResponse = useCallback(
    async (text: string) => {
      if (!settings.voice.voiceOutputEnabled) return;
      voicePlayer.stop();
      streamingVoice.stop();
      setIsSpeaking(false);
      // Remain in THINKING state while audio is synthesizing in background; switch to SPEAKING only when audio plays
      setAssistantState('THINKING');
      await voicePlayer.speakText(text, settings.voice, {
        onStart: () => {
          setIsSpeaking(true);
          setAssistantState('SPEAKING');
          logActivity('VOICE_OUTPUT', `Vocalizing response (${text.slice(0, 45)}...)`, 'INFO');
        },
        onEnded: () => {
          setIsSpeaking(false);
          setAssistantState((prev) => (prev === 'SPEAKING' || prev === 'THINKING' ? 'IDLE' : prev));
        },
        onError: (err) => {
          setIsSpeaking(false);
          setAssistantState((prev) => (prev === 'SPEAKING' || prev === 'THINKING' ? 'IDLE' : prev));
          logActivity('VOICE_ERROR', `Voice playback fault: ${err?.message || err}`, 'WARNING');
        },
      });
    },
    [settings.voice, logActivity]
  );

  // Unified Message Transmission Handler (shared across bubble and full HUD)
  const handleSendMessage = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (!trimmed || isStreaming) return;
      voicePlayer.stop();
      streamingVoice.stop();

      soundManager.play('CLICK_CUE');

      const userMessage: ChatMessage = {
        id: `msg-${Date.now()}`,
        role: 'user',
        content: trimmed,
        timestamp: new Date().toLocaleTimeString(),
        numericTimestamp: Date.now(),
        status: 'completed',
      };

      const assistantMsgId = `asst-${Date.now() + 1}`;
      const initialAssistantMessage: ChatMessage = {
        id: assistantMsgId,
        role: 'assistant',
        content: '',
        timestamp: new Date().toLocaleTimeString(),
        numericTimestamp: Date.now() + 1,
        status: 'streaming',
      };

      setMessages((prev) => [...prev, userMessage, initialAssistantMessage]);
      setIsStreaming(true);
      setAssistantState('THINKING');

      const taskId = `task-${Date.now()}`;
      // Immediate proactive voice acknowledgment
      taskNarration.acknowledgeTask(trimmed, taskId, settings.voice);

      const conversationHistory: ChatMessagePayload[] = [...messages, userMessage]
        .filter((m) => m.content.trim().length > 0)
        .slice(-15)
        .map((m) => ({
          role: m.role,
          content: m.content,
        }));

      const controller = new AbortController();
      abortControllerRef.current = controller;
      let firstTokenLogged = false;
      let firstAudioLogged = false;

      // Start low-latency streaming speech pipeline if voice output is enabled
      if (settings.voice.voiceOutputEnabled && settings.voice.autoPlayback) {
        streamingVoice.startSession(settings.voice, {
          onPlaybackStart: () => {
            setIsSpeaking(true);
            setAssistantState('SPEAKING');
            logActivity('VOICE_OUTPUT', 'Full-response voice playback started.', 'INFO');
          },
          onPlaybackComplete: () => {
            setIsSpeaking(false);
            setAssistantState((prev) => {
              if (pendingApprovalsRef.current.length > 0) return 'AWAITING_APPROVAL';
              if (isStreamingRef.current) {
                return prev === 'SPEAKING' ? 'EXECUTING' : prev;
              }
              return (prev === 'SPEAKING' || prev === 'THINKING' || prev === 'RESPONDING' || prev === 'EXECUTING' ? 'IDLE' : prev);
            });
            logActivity('VOICE_OUTPUT', 'Full-response speech playback completed.', 'INFO');
          },
          onError: (err) => {
            setIsSpeaking(false);
            setAssistantState((prev) => {
              if (pendingApprovalsRef.current.length > 0) return 'AWAITING_APPROVAL';
              return (prev === 'SPEAKING' || prev === 'THINKING' || prev === 'RESPONDING' || prev === 'EXECUTING' ? 'IDLE' : prev);
            });
            logActivity('VOICE_ERROR', `Voice synthesis error: ${err?.message || err}`, 'WARNING');
          },
          onMetricsUpdate: (metrics) => {
            if (metrics.totalTimeToPlaybackMs && !firstAudioLogged) {
              firstAudioLogged = true;
              logActivity(
                'VOICE_PERF',
                `Latency: ${metrics.totalTimeToPlaybackMs}ms (Gemini: ${metrics.geminiCompletionTimeMs || 0}ms, Synth: ${metrics.synthesisDurationMs || 0}ms) | Audio: ${metrics.totalDurationSeconds || 0}s | Words: ${metrics.wordCount || 0} | RTF: ${metrics.realTimeFactor || 0}`,
                'INFO'
              );
            }
          },
        });
      }

      await streamChatCompletion(
        conversationHistory,
        'jarvis-desktop-session',
        {
          onStart: () => {},
          onStageChange: (stage) => {
            setPerceptionProgress((prev) => ({
              ...prev,
              stage: stage as any,
              stageMessage: stage === 'ANALYZING_VISION' ? 'Analyzing visuals...' : stage,
            }));
            if (stage === 'EXECUTING') {
              setAssistantState('EXECUTING');
            } else if (stage === 'AWAITING_APPROVAL') {
              setAssistantState('AWAITING_APPROVAL');
            }
          },
          onToolCall: (toolName, stage, toolStatus) => {
            logActivity('TOOL_EXECUTION', `Invoking ${toolName} [${stage || 'RUNNING'}]...`, 'INFO');
            if (stage === 'AWAITING_APPROVAL' || toolStatus === 'requires_approval') {
              setAssistantState('AWAITING_APPROVAL');
            } else {
              setAssistantState('EXECUTING');
            }
          },
          onNarration: (narrEvent) => {
            taskNarration.handleLifecycleEvent(narrEvent, settings.voice);
          },
          onDelta: (delta) => {
            if (!firstTokenLogged) {
              firstTokenLogged = true;
              setAssistantState('RESPONDING');
              soundManager.play('RESPONSE_START');
            }
            if (settings.voice.voiceOutputEnabled && settings.voice.autoPlayback) {
              streamingVoice.appendDelta(delta);
            }
            setMessages((prev) =>
              prev.map((msg) =>
                msg.id === assistantMsgId
                  ? { ...msg, content: msg.content + delta }
                  : msg
              )
            );
          },
          onUsage: () => {},
          onComplete: (fullText, _durationMs, stage) => {
            setIsStreaming(false);
            setPerceptionProgress((prev) => ({
              ...prev,
              stage: 'IDLE',
              stageMessage: '',
            }));
            soundManager.play('RESPONSE_COMPLETE');
            setMessages((prev) =>
              prev.map((msg) =>
                msg.id === assistantMsgId
                  ? {
                      ...msg,
                      content: fullText || msg.content,
                      status: 'completed',
                    }
                  : msg
              )
            );
            pollApprovals();
            const isAwaiting = stage === 'AWAITING_APPROVAL' || pendingApprovalsRef.current.length > 0;
            if (isAwaiting) {
              setAssistantState('AWAITING_APPROVAL');
            } else if (settings.voice.voiceOutputEnabled && settings.voice.autoPlayback) {
              setAssistantState((prev) => (prev === 'RESPONDING' || prev === 'EXECUTING' ? 'THINKING' : prev));
              streamingVoice.flushAndComplete(fullText);
            } else {
              setAssistantState('IDLE');
            }
          },
          onError: (code, errorMsg) => {
            streamingVoice.stop();
            setIsStreaming(false);
            setAssistantState('ERROR');

            const lower = (errorMsg || '').toLowerCase();
            const is503 =
              code === 'UPSTREAM_TIMEOUT' ||
              lower.includes('503') ||
              lower.includes('unavailable') ||
              lower.includes('high demand') ||
              lower.includes('demand spike') ||
              lower.includes('429') ||
              lower.includes('capacity') ||
              lower.includes('overloaded');
            const cleanedMsg = (errorMsg || '')
              .replace(/\{.*?\}[\s\S]*/g, '')
              .replace(/Gemini API error:\s*/i, '')
              .trim();

            const displayMsg = is503
              ? "The upstream neural service is experiencing a temporary demand surge (503 Unavailable). Spikes are brief—please try your request again in a few moments."
              : (cleanedMsg || 'Stream error occurred.');

            setPerceptionProgress((prev) => ({
              ...prev,
              stage: 'FAILED',
              stageMessage: displayMsg,
              error: displayMsg,
            }));
            soundManager.play('ERROR_OCCURRED');
            setMessages((prev) =>
              prev.map((msg) =>
                msg.id === assistantMsgId
                  ? {
                      ...msg,
                      content: msg.content || `[Service Notice]: ${displayMsg}`,
                      status: 'error',
                    }
                  : msg
              )
            );
            logActivity(
              is503 ? 'SERVICE_NOTICE' : 'STREAM_ERROR',
              is503 ? `Upstream capacity spike: 503 Temporarily Unavailable (Standby)` : `Streaming failure [${code}]: ${cleanedMsg || errorMsg}`,
              is503 ? 'WARNING' : 'CRITICAL'
            );

            if (is503) {
              setTimeout(() => {
                setAssistantState((curr) => (curr === 'ERROR' ? 'IDLE' : curr));
              }, 2000);
            }
          },
        },
        controller.signal
      );
    },
    [isStreaming, messages, pollApprovals, logActivity, settings.voice, handleSpeakResponse]
  );

  // Compact Push-to-Talk Handler (Instant 1-Click Record & Transmit)
  const handleCompactPushToTalk = useCallback(async () => {
    soundManager.play('CLICK_CUE');
    if (isSpeaking) {
      handleStopSpeaking();
      return;
    }

    if (isRecording) {
      // 1-Click Stop & Send
      try {
        setIsRecording(false);
        setIsTranscribing(true);
        setAssistantState('THINKING');
        const audioBlob = await audioRecorder.stop();
        if (!audioBlob || audioBlob.size < 400) {
          setIsTranscribing(false);
          setAssistantState('IDLE');
          logActivity('VOICE_INPUT', 'Audio recording was empty or cancelled.', 'INFO');
          return;
        }

        const res = await transcribeAudio(audioBlob);
        setIsTranscribing(false);

        if (res.text && res.text.trim()) {
          logActivity('VOICE_INPUT', `Transcribed: "${res.text.trim()}" in ${res.duration_seconds}s`);
          // Automatically switch to quick_input view so the user immediately sees the streaming conversation
          if (viewMode === 'compact') {
            changeViewMode('quick_input');
          }
          await handleSendMessage(res.text.trim());
        } else {
          setAssistantState('IDLE');
          logActivity('VOICE_INPUT', 'Audio captured, no intelligible speech recognized.');
        }
      } catch (err: any) {
        setIsTranscribing(false);
        if (err?.message?.includes('No active recording') || err?.name === 'AbortError') {
          setAssistantState('IDLE');
          logActivity('VOICE_INPUT', 'Recording cancelled.');
        } else {
          setAssistantState('ERROR');
          logActivity('VOICE_ERROR', `Voice recognition error: ${err.message}`, 'WARNING');
        }
      }
    } else {
      // 1-Click Start Recording
      try {
        await audioRecorder.start();
        setIsRecording(true);
        setAssistantState('LISTENING');
        logActivity('VOICE_INPUT_START', 'Microphone recording started (Push-to-talk)');
      } catch (err: any) {
        setIsRecording(false);
        setAssistantState('ERROR');
        logActivity('VOICE_ERROR', `Microphone hardware error: ${err.message}`, 'CRITICAL');
      }
    }
  }, [
    isSpeaking,
    isRecording,
    handleStopSpeaking,
    viewMode,
    changeViewMode,
    handleSendMessage,
    logActivity,
  ]);

  // Automatic Recovery from Temporary FAULT State (2.5 seconds timeout)
  useEffect(() => {
    if (assistantState === 'ERROR') {
      const timer = setTimeout(() => {
        if (!isRecording && !isStreaming && !isPerceiving && !isSpeaking) {
          setAssistantState('IDLE');
        }
      }, 2500);
      return () => clearTimeout(timer);
    }
  }, [assistantState, isRecording, isStreaming, isPerceiving, isSpeaking]);

  // Unified Global & In-App Keyboard Shortcut Dispatcher
  useEffect(() => {
    const handleMicEvent = () => {
      handleCompactPushToTalk();
    };

    const handleInspectEvent = () => {
      setIsPerceptionModalOpen(true);
    };

    const handleToggleHudEvent = () => {
      changeViewMode(viewMode === 'compact' ? 'dashboard' : 'compact');
    };

    const handleKeyDown = (e: KeyboardEvent) => {
      const binds = settings.keybinds || DEFAULT_KEYBINDS;

      // 1. Push-to-Talk / Mic Toggle
      if (
        matchesKeybind(e, binds.toggleMic) ||
        e.code === 'ScrollLock' ||
        e.key === 'ScrollLock' ||
        e.code === 'Pause' ||
        e.key === 'Pause' ||
        e.key === 'F20'
      ) {
        const isInput = ['INPUT', 'TEXTAREA'].includes((e.target as HTMLElement)?.tagName);
        if (!isInput || e.ctrlKey || e.altKey) {
          e.preventDefault();
          handleCompactPushToTalk();
          return;
        }
      }

      // 2. Summon / Dismiss HUD
      if (matchesKeybind(e, binds.toggleHud)) {
        e.preventDefault();
        changeViewMode(viewMode === 'compact' ? 'dashboard' : 'compact');
        return;
      }

      // 3. Screen Perception & OCR
      if (matchesKeybind(e, binds.inspectScreen)) {
        e.preventDefault();
        setIsPerceptionModalOpen(true);
        return;
      }

      // 4. Stop Speaking / Cancel / Escape
      if (matchesKeybind(e, binds.stopSpeaking)) {
        if (isSpeaking) {
          e.preventDefault();
          handleStopSpeaking();
          return;
        }
        if (viewMode !== 'compact') {
          e.preventDefault();
          changeViewMode('compact');
          return;
        }
      }
    };

    window.addEventListener('jarvis:toggle_mic', handleMicEvent);
    window.addEventListener('jarvis:inspect_screen', handleInspectEvent);
    window.addEventListener('jarvis:toggle_hud', handleToggleHudEvent);
    window.addEventListener('keydown', handleKeyDown);

    return () => {
      window.removeEventListener('jarvis:toggle_mic', handleMicEvent);
      window.removeEventListener('jarvis:inspect_screen', handleInspectEvent);
      window.removeEventListener('jarvis:toggle_hud', handleToggleHudEvent);
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [
    handleCompactPushToTalk,
    changeViewMode,
    viewMode,
    isSpeaking,
    handleStopSpeaking,
    settings.keybinds,
  ]);

  // User-Initiated Screen Perception Cancellation
  const handleCancelPerception = useCallback(() => {
    const currentReqId = activePerceptionReqIdRef.current;
    if (!currentReqId) return;

    if (perceptionAbortControllerRef.current) {
      try {
        perceptionAbortControllerRef.current.abort();
      } catch {
        // ignore
      }
      perceptionAbortControllerRef.current = null;
    }
    if (abortControllerRef.current) {
      try {
        abortControllerRef.current.abort();
      } catch {
        // ignore
      }
      abortControllerRef.current = null;
    }

    activePerceptionReqIdRef.current = null;
    voicePlayer.stop();
    streamingVoice.stop();
    setIsSpeaking(false);
    setIsPerceiving(false);
    setIsStreaming(false);
    setAssistantState('IDLE');
    setPerceptionProgress((prev) => ({
      ...prev,
      stage: 'CANCELLED',
      stageMessage: 'Screen perception cancelled by user.',
    }));

    const cancelNotice: ChatMessage = {
      id: `notice-cancel-${Date.now()}`,
      role: 'assistant',
      content: '*[Perception Operation Cancelled by User]*',
      timestamp: new Date().toLocaleTimeString(),
      numericTimestamp: Date.now(),
      status: 'completed',
      model: 'J.A.R.V.I.S. Core',
    };
    setMessages((prev) => [...prev, cancelNotice]);
    logActivity('PERCEPTION_CANCELLED', `Request ${currentReqId} cancelled by operator`, 'INFO');
    soundManager.play('DEACTIVATION');
  }, [logActivity]);

  // Screen Perception & Multimodal Vision Lifecycle Handler
  const handlePerformPerception = useCallback(
    async (
      mode: 'ocr_only' | 'gemini_vision',
      monitorId: number,
      activeWindowOnly: boolean,
      userQuery?: string
    ) => {
      // 1. Generate Correlation ID and Setup Controllers
      const requestId = `percept-${Date.now()}-${Math.random().toString(36).substring(2, 7)}`;
      activePerceptionReqIdRef.current = requestId;

      const controller = new AbortController();
      perceptionAbortControllerRef.current = controller;
      abortControllerRef.current = controller;

      const targetDesc = activeWindowOnly ? 'Active Window' : `Monitor ${monitorId}`;
      const startTime = Date.now();

      setIsPerceiving(true);
      setAssistantState('THINKING');

      setPerceptionProgress({
        requestId,
        stage: 'CAPTURING',
        stageMessage: `Capturing desktop surface (${targetDesc})...`,
        targetDescription: targetDesc,
        mode,
        startTime,
        elapsedMs: 0,
        error: null,
      });

      try {
        if (mode === 'ocr_only') {
          // Local on-device Windows OCR
          logActivity(
            'SCREEN_OCR',
            `[${requestId}] Running on-device OCR on ${targetDesc}`,
            'INFO'
          );

          setPerceptionProgress((prev) =>
            prev.requestId === requestId
              ? {
                  ...prev,
                  stage: 'READING_OCR',
                  stageMessage: `Performing on-device OCR extraction...`,
                }
              : prev
          );

          const res = await inspectScreen({
            request_id: requestId,
            monitor_id: monitorId,
            active_window_only: activeWindowOnly,
            include_ocr: true,
            authorize_gemini_vision: false,
          });

          // Check if superseded or cancelled
          if (activePerceptionReqIdRef.current !== requestId || controller.signal.aborted) {
            return;
          }

          const ocrText = res.screen.ocr_result?.full_text || '(No text detected in target region)';
          const wordCount = res.screen.ocr_result?.word_count || 0;
          const targetName = res.screen.active_window_title || `Display ${monitorId}`;
          const durationMs =
            ((res.capture_duration_ms || 0) + (res.ocr_duration_ms || 0)) ||
            Math.round(Date.now() - startTime);

          setPerceptionProgress({
            requestId,
            stage: 'COMPLETED',
            stageMessage: `OCR completed (${wordCount} words extracted in ${durationMs}ms)`,
            targetDescription: targetName,
            mode,
            startTime,
            elapsedMs: durationMs,
            error: null,
          });

          const userMsg: ChatMessage = {
            id: `usr-ocr-${Date.now()}`,
            role: 'user',
            content: userQuery || `Read text in ${targetName}`,
            timestamp: new Date().toLocaleTimeString(),
            numericTimestamp: Date.now(),
            status: 'completed',
          };

          const assistantMsg: ChatMessage = {
            id: `asst-ocr-${Date.now() + 1}`,
            role: 'assistant',
            content: `**[Local Windows OCR Scan // ${targetName}]**\nExtracted ${wordCount} words on-device (${durationMs}ms):\n\n\`\`\`text\n${ocrText}\n\`\`\``,
            timestamp: new Date().toLocaleTimeString(),
            numericTimestamp: Date.now() + 1,
            status: 'completed',
            model: 'Windows Media OCR (Local)',
          };

          setMessages((prev) => [...prev, userMsg, assistantMsg]);
          soundManager.play('RESPONSE_COMPLETE');
          if (settings.voice.voiceOutputEnabled && settings.voice.autoPlayback) {
            setAssistantState('THINKING');
            handleSpeakResponse(`Local screen scan complete. Extracted ${wordCount} words.`);
          } else {
            setAssistantState('IDLE');
          }
        } else {
          // Gemini Multimodal Vision Reasoning
          logActivity(
            'SCREEN_VISION',
            `[${requestId}] Authorized multimodal vision transfer for ${targetDesc}`,
            'INFO'
          );

          // Phase 1: Capture & OCR
          setPerceptionProgress((prev) =>
            prev.requestId === requestId
              ? {
                  ...prev,
                  stage: 'CAPTURING',
                  stageMessage: `Capturing desktop surface for vision inspection...`,
                }
              : prev
          );

          const res = await inspectScreen({
            request_id: requestId,
            monitor_id: monitorId,
            active_window_only: activeWindowOnly,
            include_ocr: true,
            authorize_gemini_vision: true,
          });

          if (activePerceptionReqIdRef.current !== requestId || controller.signal.aborted) {
            return;
          }

          const base64Img = res.screen.image_base64;
          const prompt = userQuery || 'Explain what is currently displayed on my screen.';
          const targetName = res.screen.active_window_title || `Display ${monitorId}`;

          // Phase 2: Transmit to Gemini Vision
          setPerceptionProgress((prev) =>
            prev.requestId === requestId
              ? {
                  ...prev,
                  stage: 'ANALYZING_VISION',
                  stageMessage: `Transmitting frame to Gemini Vision neural model...`,
                  targetDescription: targetName,
                }
              : prev
          );

          const userMessage: ChatMessage = {
            id: `msg-vision-${Date.now()}`,
            role: 'user',
            content: prompt,
            timestamp: new Date().toLocaleTimeString(),
            numericTimestamp: Date.now(),
            status: 'completed',
            imagePreview: base64Img ? `data:image/jpeg;base64,${base64Img}` : undefined,
          };

          const assistantMsgId = `asst-vision-${Date.now() + 1}`;
          const initialAssistantMessage: ChatMessage = {
            id: assistantMsgId,
            role: 'assistant',
            content: '',
            timestamp: new Date().toLocaleTimeString(),
            numericTimestamp: Date.now() + 1,
            status: 'streaming',
          };

          setMessages((prev) => [...prev, userMessage, initialAssistantMessage]);
          setIsStreaming(true);
          setAssistantState('THINKING');

          const conversationHistory: ChatMessagePayload[] = [
            ...messages.filter((m) => m.content.trim().length > 0).slice(-10).map((m) => ({
              role: m.role,
              content: m.content,
            })),
            {
              role: 'user',
              content: prompt,
              image_data: base64Img,
              image_mime_type: 'image/jpeg',
            },
          ];

          let firstTokenLogged = false;

          if (settings.voice.voiceOutputEnabled && settings.voice.autoPlayback) {
            streamingVoice.startSession(settings.voice, {
              onPlaybackStart: () => {
                setIsSpeaking(true);
                setAssistantState('SPEAKING');
              },
              onPlaybackComplete: () => {
                setIsSpeaking(false);
                setAssistantState((prev) => (prev === 'SPEAKING' || prev === 'THINKING' || prev === 'RESPONDING' ? 'IDLE' : prev));
              },
              onError: (err) => {
                setIsSpeaking(false);
                setAssistantState((prev) => (prev === 'SPEAKING' || prev === 'THINKING' || prev === 'RESPONDING' ? 'IDLE' : prev));
                logActivity('VOICE_ERROR', `Streaming voice error: ${err?.message || err}`, 'WARNING');
              },
            });
          }

          await streamChatCompletion(
            conversationHistory,
            'jarvis-desktop-session',
            {
              onStart: () => {
                if (activePerceptionReqIdRef.current === requestId) {
                  setPerceptionProgress((prev) => ({
                    ...prev,
                    stage: 'ANALYZING_VISION',
                    stageMessage: 'Gemini neural model analyzing visual frame...',
                  }));
                }
              },
              onStageChange: (stage) => {
                if (activePerceptionReqIdRef.current === requestId) {
                  setPerceptionProgress((prev) => ({
                    ...prev,
                    stage: stage as any,
                    stageMessage:
                      stage === 'ANALYZING_VISION'
                        ? 'Analyzing visuals...'
                        : stage === 'GENERATING'
                        ? 'Synthesizing response...'
                        : stage,
                  }));
                }
              },
              onDelta: (delta) => {
                if (activePerceptionReqIdRef.current !== requestId) return;
                if (!firstTokenLogged) {
                  firstTokenLogged = true;
                  setAssistantState('RESPONDING');
                  setPerceptionProgress((prev) => ({
                    ...prev,
                    stage: 'GENERATING',
                    stageMessage: 'Generating visual description...',
                  }));
                  soundManager.play('RESPONSE_START');
                }
                if (settings.voice.voiceOutputEnabled && settings.voice.autoPlayback) {
                  streamingVoice.appendDelta(delta);
                }
                setMessages((prev) =>
                  prev.map((msg) =>
                    msg.id === assistantMsgId ? { ...msg, content: msg.content + delta } : msg
                  )
                );
              },
              onUsage: () => {},
              onNarration: (narrEvent) => {
                taskNarration.handleLifecycleEvent(narrEvent, settings.voice);
              },
              onComplete: (fullText) => {
                if (activePerceptionReqIdRef.current !== requestId) return;
                setIsStreaming(false);
                setPerceptionProgress((prev) => ({
                  ...prev,
                  stage: 'COMPLETED',
                  stageMessage: 'Visual analysis complete',
                  elapsedMs: Date.now() - startTime,
                }));
                soundManager.play('RESPONSE_COMPLETE');
                setMessages((prev) =>
                  prev.map((msg) =>
                    msg.id === assistantMsgId
                      ? { ...msg, content: fullText || msg.content, status: 'completed' }
                      : msg
                  )
                );
                pollApprovals();
                const isAwaiting = pendingApprovalsRef.current.length > 0;
                if (isAwaiting) {
                  setAssistantState('AWAITING_APPROVAL');
                } else if (settings.voice.voiceOutputEnabled && settings.voice.autoPlayback) {
                  setAssistantState((prev) => (prev === 'RESPONDING' ? 'THINKING' : prev));
                  streamingVoice.flushAndComplete(fullText);
                } else {
                  setAssistantState('IDLE');
                }
              },
              onError: (_code, errorMsg) => {
                if (activePerceptionReqIdRef.current !== requestId) return;
                streamingVoice.stop();
                setIsStreaming(false);
                setAssistantState('ERROR');
                const is503 = errorMsg.includes('503') || errorMsg.includes('UNAVAILABLE') || errorMsg.includes('high demand');
                const displayMsg = is503
                  ? "Upstream vision service is experiencing high demand (503). Please retry in a few moments."
                  : errorMsg;
                setPerceptionProgress((prev) => ({
                  ...prev,
                  stage: 'FAILED',
                  stageMessage: `Vision analysis: ${displayMsg}`,
                  error: displayMsg,
                }));
                soundManager.play('ERROR_OCCURRED');
                setMessages((prev) =>
                  prev.map((msg) =>
                    msg.id === assistantMsgId
                      ? { ...msg, content: msg.content || `[Vision Notice]: ${displayMsg}`, status: 'error' }
                      : msg
                  )
                );
                if (is503) {
                  setTimeout(() => {
                    setAssistantState((curr) => (curr === 'ERROR' ? 'IDLE' : curr));
                  }, 2500);
                }
              },
            },
            controller.signal
          );
        }
      } catch (err: any) {
        if (activePerceptionReqIdRef.current === requestId) {
          setAssistantState('ERROR');
          soundManager.play('ERROR_OCCURRED');
          setPerceptionProgress((prev) => ({
            ...prev,
            stage: 'FAILED',
            stageMessage: `Perception failed: ${err.message}`,
            error: err.message,
          }));
          logActivity('PERCEPTION_ERROR', `[${requestId}] Perception failed: ${err.message}`, 'CRITICAL');
        }
      } finally {
        if (activePerceptionReqIdRef.current === requestId) {
          setIsPerceiving(false);
        }
      }
    },
    [logActivity, messages, pollApprovals, settings.voice, handleSpeakResponse]
  );
  const handleApprove = useCallback(
    async (id: string) => {
      soundManager.play('ACTIVATION');
      try {
        const res = await respondToApproval(id, true);
        taskNarration.announceApprovalDecision(true, id, settings.voice);
        logActivity('APPROVAL_DECISION', `Request #${id} approved by user.`, 'INFO');
        setPendingApprovals((prev) => prev.filter((r) => r.id !== id));
        setTimeout(pollApprovals, 400);

        // Record completed confirmation message directly into conversation
        const actionSummary = res.approval?.actionSummary || 'Action';
        const confirmMsg =
          res.conversation_message ||
          `Action authorized and executed: ${actionSummary}.`;

        setMessages((prev) => [
          ...prev,
          {
            id: `msg-approve-${id}-${Date.now()}`,
            role: 'assistant',
            content: confirmMsg,
            timestamp: new Date().toLocaleTimeString(),
            numericTimestamp: Date.now(),
            status: 'completed',
            model: 'J.A.R.V.I.S. Core',
          },
        ]);

        // If execution succeeded, notify Gemini clearly that the action has completed and not to re-execute it
        const isSuccess = res.execution?.status === 'success';
        const toolName = res.approval?.toolName || 'tool';

        if (isSuccess) {
          const continuationPrompt = `[SYSTEM NOTIFICATION: The operator approved and executed '${actionSummary}'. Execution completed with status: SUCCESS. The desktop action has already been performed. Do NOT re-execute or re-propose '${toolName}'. If all user instructions are satisfied, confirm task completion to the operator. If there are subsequent steps, proceed with the next step.]`;
          await handleSendMessage(continuationPrompt);
        } else {
          setAssistantState('IDLE');
        }
      } catch (err: any) {
        logActivity('APPROVAL_ERROR', `Failed to approve #${id}: ${err.message}`, 'CRITICAL');
      }
    },
    [logActivity, pollApprovals, handleSendMessage]
  );

  const handleDecline = useCallback(
    async (id: string) => {
      soundManager.play('ERROR_OCCURRED');
      try {
        const res = await respondToApproval(id, false);
        taskNarration.announceApprovalDecision(false, id, settings.voice);
        logActivity('APPROVAL_DECISION', `Request #${id} rejected by user.`, 'WARNING');
        setPendingApprovals((prev) => prev.filter((r) => r.id !== id));
        setAssistantState('IDLE');
        
        // Add separate distinct conversation message from JARVIS
        const rejectionText =
          res.conversation_message ||
          "Understood. I've cancelled that action as requested. Nothing was changed.";
        setMessages((prev) => [
          ...prev,
          {
            id: `msg-decline-${id}-${Date.now()}`,
            role: 'assistant',
            content: rejectionText,
            timestamp: new Date().toLocaleTimeString(),
            numericTimestamp: Date.now(),
            status: 'completed',
            model: 'J.A.R.V.I.S. Core',
          },
        ]);
        setTimeout(pollApprovals, 400);
      } catch (err: any) {
        logActivity('APPROVAL_ERROR', `Failed to decline #${id}: ${err.message}`, 'CRITICAL');
        if (err.message && err.message.includes('expired')) {
          setMessages((prev) => [
            ...prev,
            {
              id: `msg-expired-${id}-${Date.now()}`,
              role: 'assistant',
              content: "The approval request expired before it was authorized. I haven't performed the action.",
              timestamp: new Date().toLocaleTimeString(),
              numericTimestamp: Date.now(),
              status: 'completed',
              model: 'J.A.R.V.I.S. Core',
            },
          ]);
        }
      }
    },
    [logActivity, pollApprovals]
  );

  // Global & In-App Keyboard Approval Shortcuts (Ctrl + Alt + Y to Approve, Ctrl + Alt + N to Deny)
  useEffect(() => {
    const handleApprovalKeyDown = (e: KeyboardEvent) => {
      if (e.ctrlKey && e.altKey) {
        if (e.key === 'y' || e.key === 'Y') {
          if (pendingApprovalsRef.current.length > 0) {
            e.preventDefault();
            const target = pendingApprovalsRef.current[0];
            handleApprove(target.id);
          }
        } else if (e.key === 'n' || e.key === 'N') {
          if (pendingApprovalsRef.current.length > 0) {
            e.preventDefault();
            const target = pendingApprovalsRef.current[0];
            handleDecline(target.id);
          }
        }
      }
    };

    const handleNativeHotkeyDecision = (e: any) => {
      const isApproved = e.detail?.approved;
      const target = pendingApprovalsRef.current[0];
      if (target) {
        if (isApproved) {
          logActivity('HOTKEY_DECISION', `Active approval #${target.id} approved via global hotkey [Ctrl+Alt+Y].`, 'INFO');
          handleApprove(target.id);
        } else {
          logActivity('HOTKEY_DECISION', `Active approval #${target.id} declined via global hotkey [Ctrl+Alt+N].`, 'WARNING');
          handleDecline(target.id);
        }
      } else {
        pollApprovals();
      }
    };

    window.addEventListener('keydown', handleApprovalKeyDown);
    window.addEventListener('jarvis:hotkey_decision', handleNativeHotkeyDecision);
    return () => {
      window.removeEventListener('keydown', handleApprovalKeyDown);
      window.removeEventListener('jarvis:hotkey_decision', handleNativeHotkeyDecision);
    };
  }, [handleApprove, handleDecline, logActivity, pollApprovals, handleSendMessage]);

  const handleStopStreaming = useCallback(() => {
    voicePlayer.stop();
    streamingVoice.stop();
    setIsSpeaking(false);
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    setIsStreaming(false);
    setAssistantState('IDLE');
    soundManager.play('CLICK_CUE');
    logActivity('STREAM_CANCELLED', 'User halted streaming generation.', 'WARNING');
  }, [logActivity]);

  const handleDismissMessage = useCallback((id: string) => {
    soundManager.play('CLICK_CUE');
    setMessages((prev) => prev.filter((m) => m.id !== id));
  }, []);

  const handleClearConversation = useCallback(() => {
    soundManager.play('CLICK_CUE');
    setMessages([
      {
        id: `welcome-${Date.now()}`,
        role: 'assistant',
        content: 'Conversation history cleared. Ready for new instructions, Sir.',
        timestamp: new Date().toLocaleTimeString(),
        status: 'completed',
        model: 'J.A.R.V.I.S. Core',
      },
    ]);
    logActivity('SESSION_RESET', 'User cleared conversational memory context.', 'INFO');
  }, [logActivity]);

  // Panel layout controls (used in dashboard mode)
  const handleToggleMinimize = (panelId: string) => {
    setSettings((prev) => {
      const pid = panelId as PanelId;
      if (!prev.panels[pid]) return prev;
      return {
        ...prev,
        panels: {
          ...prev.panels,
          [pid]: {
            ...prev.panels[pid],
            minimized: !prev.panels[pid].minimized,
          },
        },
      };
    });
  };

  const handleToggleVisibility = (panelId: string) => {
    setSettings((prev) => {
      const pid = panelId as PanelId;
      if (!prev.panels[pid]) return prev;
      return {
        ...prev,
        panels: {
          ...prev.panels,
          [pid]: {
            ...prev.panels[pid],
            visible: !prev.panels[pid].visible,
          },
        },
      };
    });
  };

  const handleMoveOrder = (panelId: string, delta: number) => {
    setSettings((prev) => {
      const pid = panelId as PanelId;
      const currentOrder = prev.panels[pid]?.order;
      if (currentOrder === undefined) return prev;

      const targetOrder = currentOrder + delta;
      return {
        ...prev,
        panels: {
          ...prev.panels,
          [pid]: {
            ...prev.panels[pid],
            order: targetOrder,
          },
        },
      };
    });
  };

  const handleResetDefaults = () => {
    soundManager.play('APPROVAL_REQUIRED');
    setSettings(DEFAULT_SETTINGS);
    saveSettings(DEFAULT_SETTINGS);
  };

  const sortedPanelKeys = useMemo(() => {
    return (Object.keys(settings.panels) as PanelId[]).sort(
      (a, b) => settings.panels[a].order - settings.panels[b].order
    );
  }, [settings.panels]);

  // --- 1. COMPACT ORB VIEW (DEFAULT / NORMAL STATE) ---
  if (viewMode === 'compact') {
    return (
      <div className="jarvis-compact-orb-root">
        {/* If an approval is pending in compact orb mode, float the interactive approval bubble right above the orb */}
        {pendingApprovals.length > 0 && (
          <div className="jarvis-compact-approval-float">
            {pendingApprovals.map((req) => (
              <ApprovalBubble
                key={req.id}
                request={req}
                onApprove={handleApprove}
                onDecline={handleDecline}
              />
            ))}
          </div>
        )}

        <div className="jarvis-compact-container">
          {/* Main Arc Reactor Orb: Clicking opens Full Dashboard */}
          <div
            className="jarvis-compact-orb pywebview-drag-region"
            onClick={() => changeViewMode('dashboard')}
            onContextMenu={(e) => {
              e.preventDefault();
              handleCompleteShutdown();
            }}
            title="JARVIS Arc Reactor (Click to open Full Holographic Dashboard | Right-click to Exit | Alt+Space)"
          >
            <ArcReactor
              assistantState={assistantState}
              latencyMs={latencyMs}
              perceptionStage={perceptionProgress.stage !== 'IDLE' ? perceptionProgress.stage : undefined}
              onActivate={() => changeViewMode('dashboard')}
              onStopSpeaking={handleStopSpeaking}
              onClearError={() => setAssistantState('IDLE')}
            />
            {assistantState === 'AWAITING_APPROVAL' && (
              <span className="jarvis-orb-badge">APPROVAL REQUIRED</span>
            )}
          </div>

          {/* Vertical Actions Column: TALK above CMD for maximum compactness */}
          <div className="jarvis-companion-actions-column">
            {/* Dedicated Push-to-Talk Button (TALK) */}
            {settings.voice.speechInputEnabled && (
              <button
                type="button"
                className={`jarvis-companion-cmd-btn jarvis-companion-mic-btn ${
                  isRecording ? 'recording' : isSpeaking ? 'speaking' : ''
                }`}
                onClick={(e) => {
                  e.stopPropagation();
                  handleCompactPushToTalk();
                }}
                title={
                  isRecording
                    ? 'Finish Recording & Send (Click to Submit)'
                    : isSpeaking
                    ? 'Silence JARVIS (Mute)'
                    : isTranscribing
                    ? 'Transcribing audio on-device...'
                    : 'Push-to-Talk (Click to Speak | Scroll Lock | Alt+M)'
                }
              >
                <span className="cmd-btn-icon">
                  {isRecording ? '🔴' : isSpeaking ? '⏹' : isTranscribing ? '⏳' : '🎙'}
                </span>
                <span className="cmd-btn-text">
                  {isRecording ? 'DONE' : isSpeaking ? 'MUTE' : isTranscribing ? 'WAIT' : 'TALK'}
                </span>
              </button>
            )}

            {/* Separate Small Button Near Bubble to Input Command (CMD) */}
            <button
              type="button"
              className="jarvis-companion-cmd-btn"
              onClick={(e) => {
                e.stopPropagation();
                changeViewMode('quick_input');
              }}
              title="Direct Command Input (Quick query without full dashboard)"
            >
              <span className="cmd-btn-icon">⌨</span>
              <span className="cmd-btn-text">CMD</span>
            </button>
          </div>
        </div>

        {isShuttingDown && (
          <div className="jarvis-shutdown-overlay">
            <div className="jarvis-shutdown-spinner" />
            <div className="jarvis-shutdown-text">TERMINATING...</div>
          </div>
        )}
      </div>
    );
  }

  // --- 1.5 QUICK COMMAND INPUT VIEW (FLOATING TEXTBOX ABOVE THE BUBBLE) ---
  if (viewMode === 'quick_input') {
    return (
      <div className="jarvis-floating-textbox-root">
        {/* The floating command textbox directly above the bubble with shared conversation & approvals */}
        <QuickCommandBar
          onOpenDashboard={() => changeViewMode('dashboard')}
          onClose={() => changeViewMode('compact')}
          onAssistantStateChange={handleStateChange}
          onLogActivity={logActivity}
          messages={messages}
          onSendMessage={handleSendMessage}
          isStreaming={isStreaming}
          onStopStreaming={handleStopStreaming}
          pendingApprovals={pendingApprovals}
          onApprove={handleApprove}
          onDecline={handleDecline}
          onDismissMessage={handleDismissMessage}
          onOpenPerception={() => setIsPerceptionModalOpen(true)}
          assistantState={assistantState}
          isSpeaking={isSpeaking}
          onStopSpeaking={handleStopSpeaking}
          onSpeakMessage={handleSpeakResponse}
          speechInputEnabled={settings.voice.speechInputEnabled}
        />

        {/* The Arc Reactor Orb at the bottom */}
        <div className="jarvis-compact-container">
          <div
            className="jarvis-compact-orb pywebview-drag-region"
            onClick={() => changeViewMode('dashboard')}
            onContextMenu={(e) => {
              e.preventDefault();
              handleCompleteShutdown();
            }}
            title="JARVIS Arc Reactor (Click to open Fullscreen Dashboard | Right-click to Exit | Alt+Space)"
          >
            <ArcReactor
              assistantState={assistantState}
              latencyMs={latencyMs}
              perceptionStage={perceptionProgress.stage !== 'IDLE' ? perceptionProgress.stage : undefined}
              onActivate={() => changeViewMode('dashboard')}
              onStopSpeaking={handleStopSpeaking}
              onClearError={() => setAssistantState('IDLE')}
            />
            {assistantState === 'AWAITING_APPROVAL' && (
              <span className="jarvis-orb-badge">APPROVAL REQUIRED</span>
            )}
          </div>

          <div className="jarvis-companion-actions-column">
            {settings.voice.speechInputEnabled && (
              <button
                type="button"
                className={`jarvis-companion-cmd-btn jarvis-companion-mic-btn ${
                  isRecording ? 'recording' : isSpeaking ? 'speaking' : ''
                }`}
                onClick={(e) => {
                  e.stopPropagation();
                  handleCompactPushToTalk();
                }}
                title={
                  isRecording
                    ? 'Finish Recording & Send (Click to Submit)'
                    : isSpeaking
                    ? 'Silence JARVIS (Mute)'
                    : isTranscribing
                    ? 'Transcribing audio on-device...'
                    : 'Push-to-Talk (Click to Speak | Scroll Lock | Alt+M)'
                }
              >
                <span className="cmd-btn-icon">
                  {isRecording ? '🔴' : isSpeaking ? '⏹' : isTranscribing ? '⏳' : '🎙'}
                </span>
                <span className="cmd-btn-text">
                  {isRecording ? 'DONE' : isSpeaking ? 'MUTE' : isTranscribing ? 'WAIT' : 'TALK'}
                </span>
              </button>
            )}

            <button
              type="button"
              className="jarvis-companion-cmd-btn active"
              onClick={(e) => {
                e.stopPropagation();
                changeViewMode('compact');
              }}
              title="Close Textbox (Esc)"
            >
              <span className="cmd-btn-icon">✕</span>
              <span className="cmd-btn-text">CLOSE</span>
            </button>
          </div>
        </div>

        {/* Screen Perception & Multimodal Vision Modal */}
        <ScreenPerceptionModal
          isOpen={isPerceptionModalOpen}
          onClose={() => setIsPerceptionModalOpen(false)}
          onPerformPerception={handlePerformPerception}
          isProcessing={isPerceiving}
          perceptionProgress={perceptionProgress}
          onCancelPerception={handleCancelPerception}
        />

        {/* Phase 5.2 Application Integrations Management Modal */}
        <ApplicationManagerModal
          isOpen={isAppManagerOpen}
          onClose={() => setIsAppManagerOpen(false)}
        />

        {isShuttingDown && (
          <div className="jarvis-shutdown-overlay">
            <div className="jarvis-shutdown-spinner" />
            <div className="jarvis-shutdown-text">TERMINATING...</div>
          </div>
        )}
      </div>
    );
  }

  // --- 2. EXPANDED TRANSLUCENT GLASS HUD ---
  if (viewMode === 'expanded') {
    return (
      <div className="jarvis-floating-hud-root">
        <div className="jarvis-floating-hud">
          {/* Draggable Header */}
          <div className="jarvis-hud-header pywebview-drag-region">
            <div className="jarvis-hud-brand">
              <span
                className="hud-pulse-dot"
                style={{
                  background:
                    assistantState === 'ERROR'
                      ? '#ef4444'
                      : assistantState === 'AWAITING_APPROVAL'
                      ? '#f59e0b'
                      : 'var(--hud-primary)',
                }}
              />
              <span className="jarvis-hud-title">J.A.R.V.I.S. // {assistantState}</span>
            </div>
            <div className="jarvis-hud-actions">
              <button
                className="hud-icon-btn"
                title="Full Dashboard"
                onClick={() => changeViewMode('dashboard')}
              >
                ⊞
              </button>
              <button
                className="hud-icon-btn"
                title="Customization Settings"
                onClick={() => setIsSettingsOpen(true)}
              >
                ⚙
              </button>
              <button
                className="hud-icon-btn"
                title="Collapse to Orb (Esc)"
                onClick={() => changeViewMode('compact')}
              >
                −
              </button>
              <button
                className="hud-icon-btn"
                title="Hide to System Tray (Alt+Space to summon)"
                onClick={() => {
                  if ((window as any).pywebview?.api?.hide_window) {
                    (window as any).pywebview.api.hide_window();
                  } else {
                    changeViewMode('compact');
                  }
                }}
              >
                👁
              </button>
              <button
                className="hud-icon-btn shutdown"
                title="Completely Shut Down JARVIS (Exit All Services)"
                onClick={handleCompleteShutdown}
              >
                ⏻
              </button>
            </div>
          </div>

          {/* Subheader: Telemetry & State */}
          <div className="jarvis-hud-top-bar">
            <div style={{ transform: 'scale(0.55)', transformOrigin: 'center' }}>
              <ArcReactor
                assistantState={assistantState}
                latencyMs={latencyMs}
                perceptionStage={perceptionProgress.stage !== 'IDLE' ? perceptionProgress.stage : undefined}
                onStopSpeaking={handleStopSpeaking}
              />
            </div>
            <div className="jarvis-hud-status-text">
              <div>
                CORE:{' '}
                <strong style={{ color: 'var(--hud-primary)' }}>
                  {connectionState === 'connected' ? 'ONLINE' : 'LINKING'}
                </strong>{' '}
                | PING: {latencyMs !== null ? `${latencyMs}ms` : '--'}
              </div>
              <div style={{ fontSize: '0.66rem', color: 'var(--hud-text-muted)' }}>
                WINDOWS 11 DESKTOP AGENT // ACTIVE
              </div>
            </div>
          </div>

          {/* Dynamic Content */}
          <div className="jarvis-hud-content">
            {assistantState === 'AWAITING_APPROVAL' ? (
              <ApprovalPreviewPanel
                onRequestApprovalState={() => handleStateChange('AWAITING_APPROVAL')}
                onClearApprovalState={() => handleStateChange('IDLE')}
              />
            ) : (
              <ConversationPanel
                onAssistantStateChange={handleStateChange}
                onLogActivity={logActivity}
                messages={messages}
                onSendMessage={handleSendMessage}
                isStreaming={isStreaming}
                onStopStreaming={handleStopStreaming}
                pendingApprovals={pendingApprovals}
                onApprove={handleApprove}
                onDecline={handleDecline}
                onClearConversation={handleClearConversation}
                onOpenPerception={() => setIsPerceptionModalOpen(true)}
                assistantState={assistantState}
                isSpeaking={isSpeaking}
                onStopSpeaking={handleStopSpeaking}
                onSpeakMessage={handleSpeakResponse}
                speechInputEnabled={settings.voice.speechInputEnabled}
              />
            )}
          </div>

          {/* Footer Bar */}
          <div className="jarvis-hud-footer">
            <button
              className="hud-link-btn"
              onClick={() =>
                handleStateChange(
                  assistantState === 'AWAITING_APPROVAL' ? 'IDLE' : 'AWAITING_APPROVAL'
                )
              }
            >
              {assistantState === 'AWAITING_APPROVAL' ? '« Return to Conversation' : 'Security Gateway »'}
            </button>
            <span className="hud-shortcut-hint">ALT+SPACE // ESC</span>
          </div>

          {/* Shutdown in Progress Overlay */}
          {isShuttingDown && (
            <div className="jarvis-shutdown-overlay">
              <div className="jarvis-shutdown-spinner" />
              <div className="jarvis-shutdown-text">TERMINATING J.A.R.V.I.S. PROTOCOLS...</div>
              <div className="jarvis-shutdown-subtext">Halting background processes & releasing system ports</div>
            </div>
          )}
        </div>

        {/* Customization Settings Modal */}
        <SettingsModal
          isOpen={isSettingsOpen}
          settings={settings}
          onUpdateSettings={(updater) => setSettings(updater)}
          onResetDefaults={handleResetDefaults}
          onClose={() => setIsSettingsOpen(false)}
        />

        {/* Screen Perception & Multimodal Vision Modal */}
        <ScreenPerceptionModal
          isOpen={isPerceptionModalOpen}
          onClose={() => setIsPerceptionModalOpen(false)}
          onPerformPerception={handlePerformPerception}
          isProcessing={isPerceiving}
          perceptionProgress={perceptionProgress}
          onCancelPerception={handleCancelPerception}
        />

        {/* Phase 5.2 Application Integrations Management Modal */}
        <ApplicationManagerModal
          isOpen={isAppManagerOpen}
          onClose={() => setIsAppManagerOpen(false)}
        />
      </div>
    );
  }

  // --- 3. FULL HOLOGRAPHIC DASHBOARD (MARK VII FLOATING HUD) ---
  return (
    <>
      <div className="scanlines" style={{ opacity: 0.12 }} />
      <div
        className={`hud-container ${settings.reducedMotion ? 'reduced-motion' : ''} ${
          settings.density === 'compact' ? 'density-compact' : ''
        }`}
        style={{
          background:
            'radial-gradient(ellipse at 50% 30%, rgba(0, 229, 255, 0.08) 0%, rgba(4, 14, 30, 0.42) 65%, rgba(2, 6, 16, 0.55) 100%), linear-gradient(rgba(0, 229, 255, 0.03) 1px, transparent 1px), linear-gradient(90deg, rgba(0, 229, 255, 0.03) 1px, transparent 1px)',
          backgroundSize: '100% 100%, 32px 32px, 32px 32px',
          backdropFilter: 'blur(22px)',
          WebkitBackdropFilter: 'blur(22px)',
          border: 'none',
          borderBottom: '1px solid rgba(0, 229, 255, 0.28)',
          boxShadow: 'inset 0 0 35px rgba(0, 229, 255, 0.06)',
          margin: 0,
          width: '100vw',
          height: '100vh',
          borderRadius: 0,
        }}
      >
        <TopStatusBar
          assistantState={assistantState}
          connectionState={connectionState}
          healthData={healthData}
          latencyMs={latencyMs}
          soundEnabled={settings.soundEnabled}
          onToggleSound={() =>
            setSettings((prev) => ({ ...prev, soundEnabled: !prev.soundEnabled }))
          }
          onOpenSettings={() => setIsSettingsOpen(true)}
          onOpenAppManager={() => setIsAppManagerOpen(true)}
          onShutdown={handleCompleteShutdown}
          onCollapseToOrb={() => changeViewMode('compact')}
          onSwitchToHUD={() => changeViewMode('expanded')}
        />

        <main className="hud-workspace">
          {/* Left Column: Telemetry & Integrity */}
          <div className="panel-column">
            {sortedPanelKeys.includes('diagnostics') && (
              <PanelContainer
                config={settings.panels.diagnostics}
                onToggleMinimize={handleToggleMinimize}
                onToggleVisibility={handleToggleVisibility}
                onMoveOrder={handleMoveOrder}
                canMoveUp={settings.panels.diagnostics.order > 0}
                canMoveDown={true}
              >
                <DiagnosticsPanel healthData={healthData} />
              </PanelContainer>
            )}

            {sortedPanelKeys.includes('systemMetrics') && (
              <PanelContainer
                config={settings.panels.systemMetrics}
                onToggleMinimize={handleToggleMinimize}
                onToggleVisibility={handleToggleVisibility}
                onMoveOrder={handleMoveOrder}
                canMoveUp={settings.panels.systemMetrics.order > 0}
                canMoveDown={true}
              >
                <SystemMetrics healthData={healthData} latencyMs={latencyMs} />
              </PanelContainer>
            )}
          </div>

          {/* Center Column: Arc Core & State Controls */}
          <section className="center-stage">
            <ArcReactor
              assistantState={assistantState}
              latencyMs={latencyMs}
              perceptionStage={perceptionProgress.stage !== 'IDLE' ? perceptionProgress.stage : undefined}
              onActivate={() => handleStateChange(assistantState === 'IDLE' ? 'LISTENING' : 'IDLE')}
              onStopSpeaking={handleStopSpeaking}
              onClearError={() => setAssistantState('IDLE')}
            />

            <div style={{ textAlign: 'center', maxWidth: '480px' }}>
              <p
                style={{
                  fontFamily: 'var(--hud-font-hud)',
                  fontSize: '0.95rem',
                  letterSpacing: '0.15em',
                  color: 'var(--hud-primary)',
                  marginBottom: '0.4rem',
                }}
              >
                J.A.R.V.I.S. DESKTOP ASSISTANT // DIAGNOSTICS DASHBOARD
              </p>
              <p style={{ fontSize: '0.85rem', color: 'var(--hud-text-muted)', lineHeight: '1.4' }}>
                Full system telemetry, modular acrylic panels, and diagnostics suite.
              </p>
            </div>

            <DevStateSimulator
              currentState={assistantState}
              onStateChange={handleStateChange}
            />

            {errorMessage && (
              <div
                style={{
                  padding: '0.7rem 1rem',
                  background: 'rgba(239, 68, 68, 0.15)',
                  border: '1px solid #ef4444',
                  borderRadius: '3px',
                  color: '#fca5a5',
                  fontFamily: 'var(--hud-font-mono)',
                  fontSize: '0.78rem',
                }}
              >
                [BACKEND LINK ALERT]: {errorMessage}
              </div>
            )}
          </section>

          {/* Right Column: Future Contracts & Event Audit Stream */}
          <div className="panel-column">
            {sortedPanelKeys.includes('conversationPreview') && (
              <PanelContainer
                config={settings.panels.conversationPreview}
                onToggleMinimize={handleToggleMinimize}
                onToggleVisibility={handleToggleVisibility}
                onMoveOrder={handleMoveOrder}
                canMoveUp={settings.panels.conversationPreview.order > 0}
                canMoveDown={true}
                badge={<span className="preview-watermark" style={{ borderColor: '#10b981', color: '#10b981' }}>LIVE SSE</span>}
              >
                <ConversationPanel
                  onAssistantStateChange={handleStateChange}
                  onLogActivity={logActivity}
                  messages={messages}
                  onSendMessage={handleSendMessage}
                  isStreaming={isStreaming}
                  onStopStreaming={handleStopStreaming}
                  pendingApprovals={pendingApprovals}
                  onApprove={handleApprove}
                  onDecline={handleDecline}
                  onClearConversation={handleClearConversation}
                  onOpenPerception={() => setIsPerceptionModalOpen(true)}
                  assistantState={assistantState}
                  isSpeaking={isSpeaking}
                  onStopSpeaking={handleStopSpeaking}
                  onSpeakMessage={handleSpeakResponse}
                  speechInputEnabled={settings.voice.speechInputEnabled}
                />
              </PanelContainer>
            )}

            {sortedPanelKeys.includes('approvalPreview') && (
              <PanelContainer
                config={settings.panels.approvalPreview}
                onToggleMinimize={handleToggleMinimize}
                onToggleVisibility={handleToggleVisibility}
                onMoveOrder={handleMoveOrder}
                canMoveUp={settings.panels.approvalPreview.order > 0}
                canMoveDown={true}
                badge={<span className="preview-watermark">PHASE 3</span>}
              >
                <ApprovalPreviewPanel
                  onRequestApprovalState={() => handleStateChange('AWAITING_APPROVAL')}
                  onClearApprovalState={() => handleStateChange('IDLE')}
                />
              </PanelContainer>
            )}

            {sortedPanelKeys.includes('activityLog') && (
              <PanelContainer
                config={settings.panels.activityLog}
                onToggleMinimize={handleToggleMinimize}
                onToggleVisibility={handleToggleVisibility}
                onMoveOrder={handleMoveOrder}
                canMoveUp={settings.panels.activityLog.order > 0}
                canMoveDown={false}
              >
                <ActivityLogPanel
                  events={activityEvents}
                  onClear={() => setActivityEvents([])}
                />
              </PanelContainer>
            )}
          </div>
        </main>

        <footer
          style={{
            marginTop: '1.5rem',
            paddingTop: '0.75rem',
            borderTop: '1px solid var(--hud-panel-border)',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            fontSize: '0.75rem',
            color: 'var(--hud-text-muted)',
            fontFamily: 'var(--hud-font-mono)',
          }}
        >
          <span>PROTOCOL MARK VII // PRESENTATION ENGINE // NO PRIVILEGED SHELL EXPOSURE</span>
          <span>SYNC: {lastChecked || 'CONNECTING...'}</span>
        </footer>

        {/* Customization Settings Modal */}
        <SettingsModal
          isOpen={isSettingsOpen}
          settings={settings}
          onUpdateSettings={(updater) => setSettings(updater)}
          onResetDefaults={handleResetDefaults}
          onClose={() => setIsSettingsOpen(false)}
        />

        {/* Screen Perception & Multimodal Vision Modal */}
        <ScreenPerceptionModal
          isOpen={isPerceptionModalOpen}
          onClose={() => setIsPerceptionModalOpen(false)}
          onPerformPerception={handlePerformPerception}
          isProcessing={isPerceiving}
          perceptionProgress={perceptionProgress}
          onCancelPerception={handleCancelPerception}
        />

        {/* Phase 5.2 Application Integrations Management Modal */}
        <ApplicationManagerModal
          isOpen={isAppManagerOpen}
          onClose={() => setIsAppManagerOpen(false)}
        />
      </div>
    </>
  );
};

export default App;
