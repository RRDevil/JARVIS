import React, { useState, useRef, useEffect, useCallback } from 'react';
import { ChatMessage, ApprovalRequest } from '../types/contracts';
import { soundManager } from '../services/soundManager';
import { SafeMarkdown } from './SafeMarkdown';
import { AssistantState } from '../types/assistantState';
import { ApprovalBubble } from './ApprovalBubble';
import { useBubbleConversation } from '../hooks/useBubbleConversation';
import { audioRecorder } from '../services/voiceService';
import { transcribeAudio } from '../services/api';

interface QuickCommandBarProps {
  onOpenDashboard: () => void;
  onClose: () => void;
  onAssistantStateChange?: (state: AssistantState) => void;
  onLogActivity?: (eventType: string, details: string, severity?: 'INFO' | 'WARNING' | 'CRITICAL') => void;
  // Shared conversation and approval props
  messages?: ChatMessage[];
  onSendMessage?: (text: string) => Promise<void>;
  isStreaming?: boolean;
  onStopStreaming?: () => void;
  pendingApprovals?: ApprovalRequest[];
  onApprove?: (id: string) => Promise<void>;
  onDecline?: (id: string) => Promise<void>;
  onDismissMessage?: (id: string) => void;
  onOpenPerception?: () => void;
  // Voice interaction props
  assistantState?: AssistantState;
  isSpeaking?: boolean;
  onStopSpeaking?: () => void;
  onSpeakMessage?: (text: string) => Promise<void>;
  speechInputEnabled?: boolean;
}

export const QuickCommandBar: React.FC<QuickCommandBarProps> = ({
  onOpenDashboard,
  onClose,
  onAssistantStateChange,
  onLogActivity,
  messages: externalMessages,
  onSendMessage,
  isStreaming: externalIsStreaming,
  onStopStreaming,
  pendingApprovals = [],
  onApprove,
  onDecline,
  onDismissMessage,
  onOpenPerception,
  assistantState,
  isSpeaking = false,
  onStopSpeaking,
  onSpeakMessage,
  speechInputEnabled = true,
}) => {
  const [prompt, setPrompt] = useState('');
  const [internalMessages, setInternalMessages] = useState<ChatMessage[]>([]);
  const [internalIsStreaming, setInternalIsStreaming] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [canScrollUp, setCanScrollUp] = useState(false);
  const [canScrollDown, setCanScrollDown] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [isTranscribing, setIsTranscribing] = useState(false);

  const inputRef = useRef<HTMLInputElement | null>(null);
  const streamContainerRef = useRef<HTMLDivElement | null>(null);

  const messages = externalMessages ?? internalMessages;
  const isStreaming = externalIsStreaming ?? internalIsStreaming;

  // Task lifecycle, status classification & progressive fade management
  const { visibleItems, dismissItem } = useBubbleConversation(messages, isStreaming, {
    completedTimeoutMs: 14000,
    recentResultTimeoutMs: 90000,
    fadeDurationMs: 750,
  });

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  // Check scroll state
  const handleScrollCheck = useCallback(() => {
    const el = streamContainerRef.current;
    if (!el) return;
    setCanScrollUp(el.scrollTop > 15);
    setCanScrollDown(el.scrollHeight - el.scrollTop - el.clientHeight > 15);
  }, []);

  // Smooth scroll helper
  const scrollByDelta = (delta: number) => {
    const el = streamContainerRef.current;
    if (!el) return;
    if (typeof el.scrollBy === 'function') {
      el.scrollBy({ top: delta, behavior: 'smooth' });
    } else {
      el.scrollTop += delta;
    }
    setTimeout(handleScrollCheck, 150);
  };

  // Auto-scroll to bottom smoothly when new tokens or bubbles arrive
  useEffect(() => {
    const el = streamContainerRef.current;
    if (el) {
      if (typeof el.scrollTo === 'function') {
        el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' });
      } else {
        el.scrollTop = el.scrollHeight;
      }
      handleScrollCheck();
    }
  }, [visibleItems, pendingApprovals, handleScrollCheck]);

  // Handle message dismissal with smooth exit animation
  const handleDismissMessage = (id: string) => {
    soundManager.play('CLICK_CUE');
    dismissItem(id);
    if (onDismissMessage) {
      onDismissMessage(id);
    } else {
      setInternalMessages((prev) => prev.filter((m) => m.id !== id));
    }
  };

  const handleStop = useCallback(() => {
    if (onStopStreaming) {
      onStopStreaming();
    } else {
      setInternalIsStreaming(false);
      onAssistantStateChange?.('IDLE');
    }
  }, [onStopStreaming, onAssistantStateChange]);

  const handleToggleRecord = async () => {
    soundManager.play('CLICK_CUE');
    if (isRecording) {
      // Stop and transcribe
      try {
        setIsRecording(false);
        setIsTranscribing(true);
        onAssistantStateChange?.('THINKING');
        const audioBlob = await audioRecorder.stop();
        const res = await transcribeAudio(audioBlob);
        if (res.text && res.text.trim()) {
          setPrompt((prev) => (prev ? `${prev} ${res.text.trim()}` : res.text.trim()));
          onLogActivity?.('VOICE_INPUT', `Transcribed: "${res.text.trim()}" in ${res.duration_seconds}s`);
        } else {
          onLogActivity?.('VOICE_INPUT', 'Audio recorded, no intelligible speech recognized.');
        }
      } catch (err: any) {
        setErrorMessage(`Transcription failed: ${err.message}`);
        onLogActivity?.('VOICE_ERROR', err.message, 'WARNING');
      } finally {
        setIsTranscribing(false);
        onAssistantStateChange?.('IDLE');
      }
    } else {
      // Start recording
      try {
        setErrorMessage(null);
        await audioRecorder.start();
        setIsRecording(true);
        onAssistantStateChange?.('LISTENING');
        onLogActivity?.('VOICE_INPUT_START', 'Microphone recording started (Push-to-talk)');
      } catch (err: any) {
        setErrorMessage(err.message);
        onAssistantStateChange?.('ERROR');
      }
    }
  };

  const handleCancelRecord = () => {
    soundManager.play('CLICK_CUE');
    audioRecorder.cancel();
    setIsRecording(false);
    setIsTranscribing(false);
    onAssistantStateChange?.('IDLE');
    onLogActivity?.('VOICE_INPUT_CANCEL', 'Microphone recording discarded');
  };

  useEffect(() => {
    return () => {
      if (audioRecorder.isRecording()) {
        audioRecorder.cancel();
      }
    };
  }, []);

  const handleSubmit = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    const trimmed = prompt.trim();
    if (!trimmed || isStreaming) return;

    // Immediately clear input field so the user can enter another prompt
    setPrompt('');
    soundManager.play('CLICK_CUE');
    setErrorMessage(null);
    onLogActivity?.('USER_COMMAND', `Executed command: ${trimmed.slice(0, 50)}`);

    if (onSendMessage) {
      try {
        await onSendMessage(trimmed);
      } catch (err: any) {
        setErrorMessage(err.message || 'Transmission failed.');
      }
    } else {
      // Standalone fallback
      const userMsg: ChatMessage = {
        id: `usr-${Date.now()}`,
        role: 'user',
        content: trimmed,
        timestamp: new Date().toLocaleTimeString(),
        numericTimestamp: Date.now(),
        status: 'completed',
      };
      setInternalMessages((prev) => [...prev, userMsg]);
    }
  };

  return (
    <div className="jarvis-floating-textbox-wrapper">
      {/* Scroll controls */}
      {(canScrollUp || canScrollDown) && (
        <div className="jarvis-floating-scroll-controls">
          <button
            type="button"
            className={`hud-scroll-btn ${!canScrollUp ? 'disabled' : ''}`}
            onClick={() => scrollByDelta(-180)}
            title="Scroll Up (▲)"
            disabled={!canScrollUp}
          >
            ▲
          </button>
          <button
            type="button"
            className={`hud-scroll-btn ${!canScrollDown ? 'disabled' : ''}`}
            onClick={() => scrollByDelta(180)}
            title="Scroll Down (▼)"
            disabled={!canScrollDown}
          >
            ▼
          </button>
        </div>
      )}

      {/* Conversation Stream directly above the textbox */}
      {(visibleItems.length > 0 || pendingApprovals.length > 0) && (
        <div
          ref={streamContainerRef}
          onScroll={handleScrollCheck}
          className="jarvis-floating-conversation-stream"
        >
          {visibleItems.map(({ message: msg, status, isFading }) => {
            const isUser = msg.role === 'user';
            const statusClass =
              status === 'Processing'
                ? 'processing'
                : status === 'Recent result'
                ? 'recent'
                : 'completed';

            return (
              <div
                key={msg.id}
                className={`floating-chat-bubble ${
                  isUser ? 'jarvis-speech-bubble-user' : 'jarvis-speech-bubble-assistant'
                } status-${statusClass} ${isFading ? 'fade-out' : ''}`}
              >
                <div className="bubble-header">
                  <span className="bubble-author">
                    {!isUser && <span className="bubble-dot" />}
                    {isUser ? 'YOU' : 'J.A.R.V.I.S.'}
                  </span>
                  <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
                    {/* Status Badge: Processing, Recent result, or Completed */}
                    <span className={`bubble-status-badge ${statusClass}`} title={`Status: ${status}`}>
                      {status === 'Processing' && <span className="status-dot" />}
                      {status === 'Recent result' && <span className="status-icon">★</span>}
                      {status === 'Completed' && <span className="status-icon">✓</span>}
                      {status.toUpperCase()}
                    </span>

                    {!isUser && status === 'Completed' && onSpeakMessage && (
                      <button
                        type="button"
                        className="bubble-close-mini"
                        onClick={() => onSpeakMessage(msg.content)}
                        title="Vocalize / Speak (TTS)"
                        style={{ color: 'var(--hud-primary)' }}
                      >
                        🔊
                      </button>
                    )}
                    {!isUser && status === 'Completed' && (
                      <button
                        type="button"
                        className="bubble-close-mini"
                        onClick={onOpenDashboard}
                        title="Open Fullscreen Dashboard"
                        style={{ color: 'var(--hud-primary)' }}
                      >
                        ⊞
                      </button>
                    )}
                    <button
                      type="button"
                      className="bubble-close-mini"
                      onClick={() => handleDismissMessage(msg.id)}
                      title="Dismiss (✕)"
                    >
                      ✕
                    </button>
                  </div>
                </div>

                <div className="bubble-content-natural">
                  {msg.imagePreview && (
                    <div style={{ marginBottom: '6px', borderRadius: '4px', overflow: 'hidden', border: '1px solid rgba(0, 229, 255, 0.4)', maxWidth: '240px' }}>
                      <img src={msg.imagePreview} alt="Screen capture" style={{ width: '100%', display: 'block' }} />
                    </div>
                  )}
                  {msg.role === 'assistant' ? (
                    msg.content.length > 0 ? (
                      <SafeMarkdown content={msg.content} />
                    ) : (
                      <span className="bubble-placeholder">Synthesizing neural response...</span>
                    )
                  ) : (
                    <div style={{ color: 'var(--chat-text-primary, #F1F3F5)', whiteSpace: 'pre-wrap', lineHeight: '1.5', fontSize: '0.84rem' }}>
                      {msg.content}
                    </div>
                  )}
                </div>
              </div>
            );
          })}

          {/* Pending Approval Interactive Bubbles */}
          {pendingApprovals.map((req) => (
            <ApprovalBubble
              key={req.id}
              request={req}
              onApprove={onApprove || (async () => {})}
              onDecline={onDecline || (async () => {})}
            />
          ))}
        </div>
      )}

      {/* Error alert if any */}
      {errorMessage && (
        <div className="quick-error-banner" style={{ width: '100%', boxSizing: 'border-box', margin: 0 }}>
          <span>[ALERT]: {errorMessage}</span>
        </div>
      )}

      {/* Floating Pill Textbox Form */}
      <form onSubmit={handleSubmit} className="jarvis-floating-textbox-form">
        <span
          className="textbox-glow-dot"
          style={{ background: isStreaming ? '#f59e0b' : 'var(--hud-primary)' }}
        />
        <input
          ref={inputRef}
          type="text"
          className="jarvis-floating-textbox-input"
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          placeholder={
            isRecording
              ? 'Listening to microphone... (Click mic to transcribe)'
              : isTranscribing
              ? 'Transcribing speech on-device...'
              : 'Ask JARVIS anything... (Enter)'
          }
          disabled={isStreaming || isRecording || isTranscribing}
          onKeyDown={(e) => {
            if (e.key === 'Escape') {
              if (isRecording) {
                handleCancelRecord();
              } else if (isStreaming) {
                handleStop();
              } else {
                onClose();
              }
            }
          }}
        />

        {/* Push-to-Talk Microphone Button */}
        {speechInputEnabled && (
          <>
            {isRecording ? (
              <div style={{ display: 'flex', gap: '3px', alignItems: 'center' }}>
                <button
                  type="button"
                  className="textbox-action-btn record active"
                  onClick={handleToggleRecord}
                  title="Stop recording and transcribe (Click)"
                  style={{ color: '#ef4444', borderColor: '#ef4444' }}
                >
                  🔴 Done
                </button>
                <button
                  type="button"
                  className="textbox-action-btn"
                  onClick={handleCancelRecord}
                  title="Discard voice recording"
                  style={{ color: '#94a3b8' }}
                >
                  ✕
                </button>
              </div>
            ) : isTranscribing ? (
              <button
                type="button"
                className="textbox-action-btn disabled"
                disabled
                title="Converting speech to text..."
                style={{ color: 'var(--hud-primary)' }}
              >
                ⏳
              </button>
            ) : (
              <button
                type="button"
                className="textbox-action-btn"
                onClick={handleToggleRecord}
                disabled={isStreaming}
                title="Push-to-Talk (Microphone input)"
                style={{ color: 'var(--hud-primary)' }}
              >
                🎙
              </button>
            )}
          </>
        )}

        {/* Active Audio Playback Stop Button */}
        {(isSpeaking || assistantState === 'SPEAKING') && onStopSpeaking && (
          <button
            type="button"
            className="textbox-action-btn stop"
            onClick={onStopSpeaking}
            title="Silence Voice Output (Stop Speaking)"
            style={{
              color: '#38bdf8',
              borderColor: '#38bdf8',
              background: 'rgba(56, 189, 248, 0.15)',
            }}
          >
            ⏹ Mute
          </button>
        )}

        {onOpenPerception && (
          <button
            type="button"
            className="textbox-action-btn perception"
            onClick={onOpenPerception}
            title="Inspect Screen / Local OCR"
            style={{ color: 'var(--hud-primary)' }}
          >
            👁
          </button>
        )}
        {isStreaming ? (
          <button
            type="button"
            className="textbox-action-btn stop"
            onClick={handleStop}
            title="Halt Generation"
          >
            ■
          </button>
        ) : (
          <button
            type="submit"
            className="textbox-action-btn submit"
            disabled={!prompt.trim()}
            title="Send (Enter)"
          >
            ➤
          </button>
        )}
        <button
          type="button"
          className="textbox-action-btn close"
          onClick={onClose}
          title="Close (Esc)"
        >
          ✕
        </button>
      </form>
    </div>
  );
};
