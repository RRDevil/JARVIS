import React, { useState } from 'react';
import { ChatMessage } from '../types/contracts';
import { soundManager } from '../services/soundManager';

interface ConversationPreviewPanelProps {
  onSimulateThinking?: () => void;
}

export const ConversationPreviewPanel: React.FC<ConversationPreviewPanelProps> = ({
  onSimulateThinking,
}) => {
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: 'msg-1',
      role: 'assistant',
      content: 'Good day, Sir. All primary diagnostic channels are operational. Systems on standby.',
      timestamp: '11:58:00',
      status: 'completed',
      model: 'JARVIS Core v0.1.0',
    },
    {
      id: 'msg-2',
      role: 'user',
      content: 'Status report on local security perimeter and available subsystems.',
      timestamp: '11:58:45',
      status: 'completed',
    },
    {
      id: 'msg-3',
      role: 'assistant',
      content:
        'Localhost loopback boundary is strictly enforced. SQLite persistence is initialized. Windows UI Automation is primed for Phase 4 deployment.',
      timestamp: '11:59:02',
      status: 'completed',
      model: 'JARVIS Core v0.1.0',
    },
  ]);

  const [inputPrompt, setInputPrompt] = useState('');
  const [isTyping, setIsTyping] = useState(false);

  const handleSendPrompt = (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputPrompt.trim() || isTyping) return;

    soundManager.play('CLICK_CUE');
    const userMsg: ChatMessage = {
      id: `msg-${Date.now()}`,
      role: 'user',
      content: inputPrompt.trim(),
      timestamp: new Date().toLocaleTimeString(),
      status: 'completed',
    };

    setMessages((prev) => [...prev, userMsg]);
    setInputPrompt('');
    setIsTyping(true);

    if (onSimulateThinking) onSimulateThinking();

    // Simulate streaming token response in preview mode
    setTimeout(() => {
      soundManager.play('RESPONSE_START');
      const assistantMsg: ChatMessage = {
        id: `msg-${Date.now() + 1}`,
        role: 'assistant',
        content: `[PREVIEW CONTRACT RESPONSE]: Acknowledged. In Phase 2, this slot connects to the official Google Gemini SDK streaming endpoint. Received query: "${userMsg.content}"`,
        timestamp: new Date().toLocaleTimeString(),
        status: 'completed',
        model: 'Gemini 2.5 Flash (Contract Preview)',
      };
      setMessages((prev) => [...prev, assistantMsg]);
      setIsTyping(false);
      soundManager.play('RESPONSE_COMPLETE');
    }, 1200);
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
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
        <span>CONVERSATION STREAM</span>
        <span className="preview-watermark">PHASE 2 CONTRACT</span>
      </div>

      <div
        style={{
          maxHeight: '190px',
          overflowY: 'auto',
          display: 'flex',
          flexDirection: 'column',
          gap: '0.5rem',
        }}
      >
        {messages.map((m) => (
          <div
            key={m.id}
            style={{
              padding: '0.5rem 0.65rem',
              borderRadius: '3px',
              fontFamily: m.role === 'assistant' ? 'var(--hud-font-mono)' : 'var(--hud-font-body)',
              fontSize: '0.8rem',
              background: m.role === 'user' ? 'rgba(0, 229, 255, 0.08)' : 'rgba(0, 0, 0, 0.45)',
              border: `1px solid ${m.role === 'user' ? 'var(--hud-primary)' : 'var(--hud-dim)'}`,
              alignSelf: m.role === 'user' ? 'flex-end' : 'flex-start',
              maxWidth: '92%',
            }}
          >
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                fontSize: '0.68rem',
                color: m.role === 'user' ? 'var(--hud-primary)' : '#93c5fd',
                marginBottom: '0.2rem',
              }}
            >
              <span>{m.role === 'user' ? 'USER' : 'JARVIS CORE'}</span>
              <span>{m.timestamp}</span>
            </div>
            <div style={{ color: 'var(--hud-text)', lineHeight: '1.3' }}>{m.content}</div>
          </div>
        ))}

        {isTyping && (
          <div
            style={{
              padding: '0.4rem 0.6rem',
              fontFamily: 'var(--hud-font-mono)',
              fontSize: '0.75rem',
              color: 'var(--hud-primary)',
              fontStyle: 'italic',
            }}
          >
            SYNTHESIZING RESPONSE TOKENS...
          </div>
        )}
      </div>

      <form onSubmit={handleSendPrompt} style={{ display: 'flex', gap: '0.4rem' }}>
        <input
          type="text"
          value={inputPrompt}
          onChange={(e) => setInputPrompt(e.target.value)}
          placeholder="Enter prompt to preview contract response..."
          style={{
            flex: 1,
            background: 'rgba(0, 0, 0, 0.4)',
            border: '1px solid var(--hud-dim)',
            color: 'var(--hud-text)',
            padding: '0.4rem 0.6rem',
            fontFamily: 'var(--hud-font-mono)',
            fontSize: '0.78rem',
            borderRadius: '2px',
            outline: 'none',
          }}
        />
        <button
          type="submit"
          className="hud-btn"
          style={{ padding: '0.4rem 0.75rem', fontSize: '0.72rem' }}
          disabled={isTyping}
        >
          SEND
        </button>
      </form>
    </div>
  );
};

