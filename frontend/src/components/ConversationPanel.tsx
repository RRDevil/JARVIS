import React, { useState, useRef, useEffect, useCallback } from 'react';
import { ChatMessage, ApprovalRequest } from '../types/contracts';
import { streamChatCompletion, ChatMessagePayload, StreamUsageMetadata } from '../services/chatStream';
import { soundManager } from '../services/soundManager';
import { SafeMarkdown } from './SafeMarkdown';
import { AssistantState } from '../types/assistantState';
import { ApprovalBubble } from './ApprovalBubble';
import { audioRecorder } from '../services/voiceService';
import { transcribeAudio } from '../services/api';

interface ConversationPanelProps {
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
  onClearConversation?: () => void;
  onOpenPerception?: () => void;
  // Voice interaction props
  assistantState?: AssistantState;
  isSpeaking?: boolean;
  onStopSpeaking?: () => void;
  onSpeakMessage?: (text: string) => Promise<void>;
  speechInputEnabled?: boolean;
}

export const ConversationPanel: React.FC<ConversationPanelProps> = ({
  onAssistantStateChange,
  onLogActivity,
  messages: externalMessages,
  onSendMessage: externalOnSendMessage,
  isStreaming: externalIsStreaming,
  onStopStreaming: externalOnStopStreaming,
  pendingApprovals = [],
  onApprove,
  onDecline,
  onClearConversation,
  onOpenPerception,
  assistantState,
  isSpeaking = false,
  onStopSpeaking,
  onSpeakMessage,
  speechInputEnabled = true,
}) => {
  const [internalMessages, setInternalMessages] = useState<ChatMessage[]>([
    {
      id: 'welcome-0',
      role: 'assistant',
      content:
        'Good day, Sir. JARVIS conversational streaming interface is online. ' +
        'How may I assist you with your desktop operations today?',
      timestamp: new Date().toLocaleTimeString(),
      status: 'completed',
      model: 'J.A.R.V.I.S. Core',
    },
  ]);

  const [inputPrompt, setInputPrompt] = useState('');
  const [internalIsStreaming, setInternalIsStreaming] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isRecording, setIsRecording] = useState(false);
  const [isTranscribing, setIsTranscribing] = useState(false);
  const [lastMetrics, setLastMetrics] = useState<{
    model?: string;
    durationMs?: number;
    ttftMs?: number;
    usage?: StreamUsageMetadata;
  } | null>(null);

  const messages = externalMessages ?? internalMessages;
  const isStreaming = externalIsStreaming ?? internalIsStreaming;

  const abortControllerRef = useRef<AbortController | null>(null);
  const scrollContainerRef = useRef<HTMLDivElement | null>(null);
  const isNearBottomRef = useRef(true);

  // Auto-scroll handler
  const handleScroll = () => {
    if (!scrollContainerRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = scrollContainerRef.current;
    isNearBottomRef.current = scrollHeight - scrollTop - clientHeight < 60;
  };

  useEffect(() => {
    if (isNearBottomRef.current && scrollContainerRef.current) {
      scrollContainerRef.current.scrollTop = scrollContainerRef.current.scrollHeight;
    }
  }, [messages]);

  const handleStopGeneration = useCallback(() => {
    if (externalOnStopStreaming) {
      externalOnStopStreaming();
      return;
    }
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    setInternalIsStreaming(false);
    onAssistantStateChange?.('IDLE');
    soundManager.play('CLICK_CUE');
    onLogActivity?.('STREAM_CANCELLED', 'User halted streaming generation.', 'WARNING');
  }, [externalOnStopStreaming, onAssistantStateChange, onLogActivity]);

  const handleToggleRecord = async () => {
    soundManager.play('CLICK_CUE');
    if (isRecording) {
      try {
        setIsRecording(false);
        setIsTranscribing(true);
        onAssistantStateChange?.('THINKING');
        const audioBlob = await audioRecorder.stop();
        const res = await transcribeAudio(audioBlob);
        if (res.text && res.text.trim()) {
          setInputPrompt((prev) => (prev ? `${prev} ${res.text.trim()}` : res.text.trim()));
          onLogActivity?.('VOICE_INPUT', `Transcribed: "${res.text.trim()}" in ${res.duration_seconds}s`);
        } else {
          onLogActivity?.('VOICE_INPUT', 'Audio captured, no intelligible speech recognized.');
        }
      } catch (err: any) {
        setErrorMessage(`Transcription failed: ${err.message}`);
        onLogActivity?.('VOICE_ERROR', err.message, 'WARNING');
      } finally {
        setIsTranscribing(false);
        onAssistantStateChange?.('IDLE');
      }
    } else {
      try {
        setErrorMessage(null);
        await audioRecorder.start();
        setIsRecording(true);
        onAssistantStateChange?.('LISTENING');
        onLogActivity?.('VOICE_INPUT_START', 'Microphone recording started');
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

  const handleSendMessage = async (textToSend?: string) => {
    const text = (textToSend ?? inputPrompt).trim();
    if (!text || isStreaming) return;

    if (externalOnSendMessage) {
      setInputPrompt('');
      try {
        await externalOnSendMessage(text);
      } catch (err: any) {
        setErrorMessage(err.message || 'Transmission failed.');
      }
      return;
    }

    soundManager.play('CLICK_CUE');
    setErrorMessage(null);

    const userMessage: ChatMessage = {
      id: `msg-${Date.now()}`,
      role: 'user',
      content: text,
      timestamp: new Date().toLocaleTimeString(),
      status: 'completed',
    };

    const assistantMsgId = `asst-${Date.now() + 1}`;
    const initialAssistantMessage: ChatMessage = {
      id: assistantMsgId,
      role: 'assistant',
      content: '',
      timestamp: new Date().toLocaleTimeString(),
      status: 'streaming',
    };

    setInternalMessages((prev) => [...prev, userMessage, initialAssistantMessage]);
    setInputPrompt('');
    setInternalIsStreaming(true);
    onAssistantStateChange?.('THINKING');

    // Prepare context messages for upstream payload
    const conversationHistory: ChatMessagePayload[] = [...messages, userMessage]
      .filter((m) => m.content.trim().length > 0)
      .slice(-15) // Keep bounded context of last 15 messages
      .map((m) => ({
        role: m.role,
        content: m.content,
      }));

    const controller = new AbortController();
    abortControllerRef.current = controller;
    const startTime = performance.now();
    let firstTokenLogged = false;

    await streamChatCompletion(
      conversationHistory,
      'jarvis-desktop-session',
      {
        onStart: (model) => {
          setLastMetrics((prev) => ({ ...prev, model }));
        },
        onDelta: (delta) => {
          if (!firstTokenLogged) {
            firstTokenLogged = true;
            onAssistantStateChange?.('RESPONDING');
            soundManager.play('RESPONSE_START');
          }
          setInternalMessages((prev) =>
            prev.map((msg) =>
              msg.id === assistantMsgId
                ? { ...msg, content: msg.content + delta }
                : msg
            )
          );
        },
        onUsage: (usage) => {
          setLastMetrics((prev) => ({ ...prev, usage }));
        },
        onComplete: (fullText, durationMs) => {
          setInternalIsStreaming(false);
          onAssistantStateChange?.('IDLE');
          soundManager.play('RESPONSE_COMPLETE');
          const elapsed = durationMs ?? Math.round(performance.now() - startTime);

          setLastMetrics((prev) => ({ ...prev, durationMs: elapsed }));

          setInternalMessages((prev) =>
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

          onLogActivity?.(
            'CONVERSATION_TURN',
            `Turn completed in ${elapsed}ms. Response tokens streamed.`,
            'INFO'
          );
        },
        onError: (code, errorMsg) => {
          setInternalIsStreaming(false);
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
            ? 'The upstream neural service is experiencing a temporary demand surge (503 Unavailable). Spikes are brief—please try your request again in a few moments.'
            : (cleanedMsg || 'Stream error occurred.');

          onAssistantStateChange?.('ERROR');
          soundManager.play('ERROR_OCCURRED');
          setErrorMessage(displayMsg);

          setInternalMessages((prev) =>
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

          onLogActivity?.(
            is503 ? 'SERVICE_NOTICE' : 'STREAM_ERROR',
            is503 ? 'Upstream capacity spike: 503 Temporarily Unavailable (Standby)' : `Streaming failure [${code}]: ${cleanedMsg || errorMsg}`,
            is503 ? 'WARNING' : 'CRITICAL'
          );

          if (is503) {
            setTimeout(() => {
              onAssistantStateChange?.('IDLE');
            }, 2000);
          }
        },
      },
      controller.signal
    );
  };

  const handleRetryLast = () => {
    // Find last user message
    const lastUserMsg = [...messages].reverse().find((m) => m.role === 'user');
    if (!lastUserMsg) return;

    if (externalOnSendMessage) {
      handleSendMessage(lastUserMsg.content);
      return;
    }

    // Remove failed assistant message from list
    setInternalMessages((prev) => {
      const idx = prev.findIndex((m) => m.id === lastUserMsg.id);
      return prev.slice(0, idx);
    });

    handleSendMessage(lastUserMsg.content);
  };

  const handleClearConversation = () => {
    soundManager.play('CLICK_CUE');
    if (onClearConversation) {
      onClearConversation();
    } else {
      setInternalMessages([
        {
          id: `welcome-${Date.now()}`,
          role: 'assistant',
          content: 'Conversation history cleared. Ready for new instructions, Sir.',
          timestamp: new Date().toLocaleTimeString(),
          status: 'completed',
          model: 'J.A.R.V.I.S. Core',
        },
      ]);
    }
    setErrorMessage(null);
    setLastMetrics(null);
    onLogActivity?.('SESSION_RESET', 'User cleared conversational memory context.', 'INFO');
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.65rem' }}>
      {/* Header bar */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          fontSize: '0.72rem',
          color: 'var(--hud-text-muted)',
          paddingBottom: '0.3rem',
          borderBottom: '1px solid var(--hud-dim)',
        }}
      >
        <span>
          CONVERSATION {lastMetrics?.model && `// ${lastMetrics.model}`}
        </span>
        <button
          onClick={handleClearConversation}
          style={{
            background: 'transparent',
            border: 'none',
            color: 'var(--hud-text-muted)',
            cursor: 'pointer',
            fontSize: '0.7rem',
            textDecoration: 'underline',
          }}
          title="Clear current session dialogue"
        >
          Reset Session
        </button>
      </div>

      {/* Message stream viewport */}
      <div
        ref={scrollContainerRef}
        onScroll={handleScroll}
        className="jarvis-chat-container"
      >
        {messages.map((m) => {
          const isUser = m.role === 'user';
          return (
            <div
              key={m.id}
              className={isUser ? 'jarvis-speech-bubble-user' : 'jarvis-speech-bubble-assistant'}
              style={{
                borderColor: m.status === 'error' ? '#ef4444' : undefined,
              }}
            >
              <div className="bubble-header">
                <span className="bubble-author">
                  {!isUser && <span className="bubble-dot" />}
                  {isUser ? 'USER' : 'J.A.R.V.I.S.'}
                </span>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  {!isUser && m.status === 'completed' && onSpeakMessage && (
                    <button
                      type="button"
                      onClick={() => onSpeakMessage(m.content)}
                      title="Vocalize / Speak (TTS)"
                      style={{
                        background: 'transparent',
                        border: 'none',
                        color: 'var(--chat-accent-cyan, #00e5ff)',
                        cursor: 'pointer',
                        fontSize: '0.78rem',
                        padding: 0,
                      }}
                    >
                      🔊
                    </button>
                  )}
                  <span className="bubble-timestamp">{m.timestamp}</span>
                </div>
              </div>

              <div className="bubble-content">
                {m.imagePreview && (
                  <div style={{ marginBottom: '6px', borderRadius: '4px', overflow: 'hidden', border: '1px solid rgba(0, 229, 255, 0.4)', maxWidth: '280px' }}>
                    <img src={m.imagePreview} alt="Screen capture" style={{ width: '100%', display: 'block' }} />
                  </div>
                )}
                {m.role === 'assistant' ? (
                  m.content ? (
                    <SafeMarkdown content={m.content} />
                  ) : m.status === 'streaming' ? (
                    <div className="bubble-placeholder">
                      Synthesizing neural response...
                    </div>
                  ) : (
                    <div className="bubble-placeholder" style={{ opacity: 0.75 }}>
                      Action prepared. Awaiting authorization...
                    </div>
                  )
                ) : (
                  <div style={{ color: 'var(--chat-text-primary, #F1F3F5)', whiteSpace: 'pre-wrap', lineHeight: '1.5', fontSize: '0.84rem' }}>
                    {m.content}
                  </div>
                )}
              </div>
            </div>
          );
        })}

        {/* Pending Approvals Interactive Bubbles */}
        {pendingApprovals.map((req) => (
          <ApprovalBubble
            key={req.id}
            request={req}
            onApprove={onApprove || (async () => {})}
            onDecline={onDecline || (async () => {})}
          />
        ))}
      </div>

      {/* Metrics Banner */}
      {lastMetrics && (
        <div className="jarvis-metrics-banner">
          <span>LATENCY: {lastMetrics.durationMs ? `${lastMetrics.durationMs}ms` : '--'}</span>
          {lastMetrics.usage && (
            <span>
              TOKENS: In:{lastMetrics.usage.input_tokens ?? '--'} | Out:
              {lastMetrics.usage.output_tokens ?? '--'}
            </span>
          )}
        </div>
      )}

      {/* Error / Retry Banner */}
      {errorMessage && (
        <div className="jarvis-error-banner">
          <span>{errorMessage}</span>
          <button
            onClick={handleRetryLast}
            className="hud-btn danger"
            style={{ padding: '0.2rem 0.5rem', fontSize: '0.68rem' }}
          >
            Retry
          </button>
        </div>
      )}

      {/* Input box & Controls */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
        <textarea
          value={inputPrompt}
          onChange={(e) => setInputPrompt(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={
            isRecording
              ? 'Listening to microphone... (Click mic to transcribe)'
              : isTranscribing
              ? 'Transcribing audio on-device...'
              : 'Direct JARVIS (Enter to send, Shift+Enter for newline)...'
          }
          rows={2}
          disabled={isStreaming || isRecording || isTranscribing}
          className="jarvis-chat-textarea"
        />

        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span style={{ fontSize: '0.68rem', color: 'var(--hud-text-muted)' }}>
            Context Limit: Bounded to 15 turns
          </span>

          <div style={{ display: 'flex', gap: '0.4rem', alignItems: 'center' }}>
            {/* Push-to-Talk Microphone Button */}
            {speechInputEnabled && (
              <>
                {isRecording ? (
                  <div style={{ display: 'flex', gap: '3px', alignItems: 'center' }}>
                    <button
                      type="button"
                      className="hud-btn"
                      onClick={handleToggleRecord}
                      title="Stop and Transcribe"
                      style={{ padding: '0.35rem 0.6rem', fontSize: '0.72rem', borderColor: '#ef4444', color: '#ef4444' }}
                    >
                      🔴 Done
                    </button>
                    <button
                      type="button"
                      className="hud-btn"
                      onClick={handleCancelRecord}
                      title="Discard Recording"
                      style={{ padding: '0.35rem 0.4rem', fontSize: '0.72rem', color: '#94a3b8' }}
                    >
                      ✕
                    </button>
                  </div>
                ) : isTranscribing ? (
                  <button
                    type="button"
                    className="hud-btn disabled"
                    disabled
                    style={{ padding: '0.35rem 0.6rem', fontSize: '0.72rem' }}
                  >
                    ⏳
                  </button>
                ) : (
                  <button
                    type="button"
                    className="hud-btn"
                    onClick={handleToggleRecord}
                    disabled={isStreaming}
                    title="Push-to-Talk (Microphone input)"
                    style={{ padding: '0.35rem 0.65rem', fontSize: '0.72rem', borderColor: 'rgba(56, 189, 248, 0.4)' }}
                  >
                    🎙 Mic
                  </button>
                )}
              </>
            )}

            {/* Stop Speaking / Silence Audio */}
            {(isSpeaking || assistantState === 'SPEAKING') && onStopSpeaking && (
              <button
                type="button"
                className="hud-btn"
                onClick={onStopSpeaking}
                title="Silence Voice Output (Stop Speaking)"
                style={{ padding: '0.35rem 0.65rem', fontSize: '0.72rem', borderColor: '#38bdf8', color: '#38bdf8', background: 'rgba(56, 189, 248, 0.15)' }}
              >
                ⏹ Silence
              </button>
            )}

            {onOpenPerception && (
              <button
                type="button"
                className="hud-btn"
                onClick={onOpenPerception}
                disabled={isStreaming}
                title="Inspect Screen / Local OCR"
                style={{ padding: '0.35rem 0.65rem', fontSize: '0.72rem', borderColor: 'rgba(0, 229, 255, 0.4)' }}
              >
                👁 Screen
              </button>
            )}
            {isStreaming ? (
              <button
                type="button"
                className="hud-btn danger"
                onClick={handleStopGeneration}
                style={{ padding: '0.35rem 0.75rem', fontSize: '0.72rem' }}
              >
                Halt Stream
              </button>
            ) : (
              <button
                type="button"
                className="hud-btn"
                onClick={() => handleSendMessage()}
                disabled={!inputPrompt.trim()}
                style={{ padding: '0.35rem 0.9rem', fontSize: '0.72rem' }}
              >
                Transmit
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

