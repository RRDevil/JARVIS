import React from 'react';
import { AuditEvent } from '../types/contracts';

interface ActivityLogPanelProps {
  events: AuditEvent[];
  onClear?: () => void;
}

export const ActivityLogPanel: React.FC<ActivityLogPanelProps> = ({ events, onClear }) => {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem' }}>
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          fontSize: '0.75rem',
          color: 'var(--hud-text-muted)',
          paddingBottom: '0.3rem',
          borderBottom: '1px solid var(--hud-dim)',
        }}
      >
        <span>EVENT STREAM ({events.length})</span>
        {onClear && (
          <button
            onClick={onClear}
            style={{
              background: 'transparent',
              border: 'none',
              color: 'var(--hud-text-muted)',
              cursor: 'pointer',
              fontSize: '0.7rem',
              textDecoration: 'underline',
            }}
          >
            Clear Local Log
          </button>
        )}
      </div>

      <div
        style={{
          maxHeight: '190px',
          overflowY: 'auto',
          display: 'flex',
          flexDirection: 'column',
          gap: '0.4rem',
        }}
      >
        {events.length === 0 ? (
          <p style={{ color: 'var(--hud-text-muted)', fontSize: '0.8rem', fontStyle: 'italic' }}>
            No activity recorded yet.
          </p>
        ) : (
          events.map((ev) => (
            <div
              key={ev.id}
              style={{
                padding: '0.4rem 0.5rem',
                background: 'rgba(0, 0, 0, 0.35)',
                borderLeft: `2px solid ${
                  ev.severity === 'CRITICAL'
                    ? '#ef4444'
                    : ev.severity === 'WARNING'
                    ? '#f59e0b'
                    : 'var(--hud-primary)'
                }`,
                borderRadius: '2px',
                fontFamily: 'var(--hud-font-mono)',
                fontSize: '0.75rem',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.15rem' }}>
                <span
                  style={{
                    color:
                      ev.severity === 'CRITICAL'
                        ? '#ef4444'
                        : ev.severity === 'WARNING'
                        ? '#f59e0b'
                        : 'var(--hud-primary)',
                    fontWeight: 700,
                  }}
                >
                  [{ev.eventType}]
                </span>
                <span style={{ color: 'var(--hud-text-muted)', fontSize: '0.7rem' }}>
                  {ev.timestamp}
                </span>
              </div>
              <div style={{ color: 'var(--hud-text)', lineHeight: '1.3' }}>
                {ev.details}
                {ev.isSimulated && <span className="preview-watermark">PREVIEW</span>}
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
};

