import React, { useState } from 'react';
import { ApprovalRequest } from '../types/contracts';

interface ApprovalBubbleProps {
  request: ApprovalRequest;
  onApprove: (id: string) => Promise<void>;
  onDecline: (id: string) => Promise<void>;
}

export const ApprovalBubble: React.FC<ApprovalBubbleProps> = ({
  request,
  onApprove,
  onDecline,
}) => {
  const [loading, setLoading] = useState(false);
  const [localStatus, setLocalStatus] = useState<'pending' | 'approved' | 'declined'>(
    request.status === 'approved' ? 'approved' : request.status === 'rejected' ? 'declined' : 'pending'
  );

  const handleApproveClick = async () => {
    if (loading || localStatus !== 'pending') return;
    setLoading(true);
    try {
      await onApprove(request.id);
      setLocalStatus('approved');
    } finally {
      setLoading(false);
    }
  };

  const handleDeclineClick = async () => {
    if (loading || localStatus !== 'pending') return;
    setLoading(true);
    try {
      await onDecline(request.id);
      setLocalStatus('declined');
    } finally {
      setLoading(false);
    }
  };

  const status = localStatus !== 'pending' ? localStatus : request.status === 'approved' ? 'approved' : request.status === 'rejected' ? 'declined' : 'pending';

  // Extract application target, window title, and shortcut keys for focus awareness
  const targetApp = request.parameters?.app_name || request.parameters?.target_app_name || request.parameters?.app_id;
  const windowTitle = request.parameters?.window_title;
  const expectedPid = request.parameters?.expected_process_id;
  const shortcutKeys = request.parameters?.keys;
  const shortcutDisplay = Array.isArray(shortcutKeys) ? shortcutKeys.join(' + ') : shortcutKeys;
  const isShortcutOrInteraction =
    request.toolName.includes('shortcut') ||
    request.toolName.includes('click') ||
    request.toolName.includes('ui_');

  // Visual Grounding Target Resolution properties
  const hasCoords = request.parameters?.x !== undefined && request.parameters?.y !== undefined;
  const coordsDisplay = hasCoords ? `(${request.parameters.x}, ${request.parameters.y})` : null;
  const bbox = request.parameters?.bounding_box;
  const bboxDisplay = bbox && bbox.width ? `${bbox.width}×${bbox.height} at (${bbox.left}, ${bbox.top})` : null;
  const detMethod = request.parameters?.detection_method;
  const methodLabel =
    detMethod === 'visual_reasoning'
      ? 'Visual AI 🧠'
      : detMethod === 'uia'
      ? 'UI Automation 🏛️'
      : detMethod === 'ocr'
      ? 'Local OCR 🔤'
      : detMethod === 'hybrid'
      ? 'Hybrid Grounding 🎯'
      : detMethod === 'coordinate'
      ? 'Direct Coords 📍'
      : detMethod;
  const confidence = request.parameters?.confidence;
  const confidenceDisplay = confidence ? `${Math.round(confidence * 100)}% match` : null;

  return (
    <div className="jarvis-approval-bubble" data-testid={`approval-bubble-${request.id}`}>
      <div className="approval-bubble-header">
        <div className="approval-badge-group">
          <span className="approval-pulse-dot" />
          <span className="approval-badge">{request.riskTier} RISK</span>
          <span className="approval-hotkey-pill" title="Global hotkeys Ctrl+Alt+Y (Approve) and Ctrl+Alt+N (Deny) available anytime">
            ⚡ GLOBAL HOTKEYS READY
          </span>
        </div>
        <span className="approval-time">
          {request.requestedAt ? new Date(request.requestedAt).toLocaleTimeString() : 'Pending'}
        </span>
      </div>

      <div className="approval-bubble-summary">
        {request.actionSummary}
      </div>

      {/* Target Application & Focus Information */}
      {targetApp && (
        <div
          className="approval-target-app-box"
          style={{
            background: 'rgba(0, 0, 0, 0.4)',
            padding: '6px 10px',
            borderRadius: '6px',
            margin: '6px 0',
            border: '1px solid rgba(245, 158, 11, 0.25)',
          }}
        >
          <div style={{ fontSize: '0.74rem', color: '#67e8f9', display: 'flex', alignItems: 'center', gap: '6px' }}>
            <span>🖥️ Target Application:</span>
            <strong style={{ color: '#ffffff', letterSpacing: '0.04em' }}>{targetApp}</strong>
            {expectedPid && (
              <span style={{ opacity: 0.65, fontSize: '0.68rem', fontFamily: 'monospace' }}>
                (PID: {expectedPid})
              </span>
            )}
          </div>
          {windowTitle && (
            <div style={{ fontSize: '0.69rem', color: '#cbd5e1', marginTop: '3px' }}>
              Target Window: <em style={{ color: '#fef08a' }}>"{windowTitle}"</em>
            </div>
          )}
        </div>
      )}

      {/* Shortcut Action Highlight */}
      {shortcutDisplay && (
        <div style={{ fontSize: '0.74rem', color: '#fbbf24', margin: '4px 0 6px 0', display: 'flex', alignItems: 'center', gap: '6px' }}>
          <span>⌨️ Action Shortcut:</span>
          <kbd
            style={{
              background: '#0f172a',
              padding: '2px 8px',
              borderRadius: '4px',
              border: '1px solid #38bdf8',
              color: '#38bdf8',
              fontFamily: 'monospace',
              fontWeight: 700,
              fontSize: '0.74rem',
            }}
          >
            {shortcutDisplay}
          </kbd>
        </div>
      )}

      {/* Exact Text Entry Payload Verification */}
      {request.parameters?.text !== undefined && (
        <div
          className="approval-text-payload-box"
          style={{
            background: 'rgba(0, 0, 0, 0.45)',
            padding: '6px 10px',
            borderRadius: '6px',
            margin: '6px 0',
            border: '1px solid rgba(56, 189, 248, 0.35)',
          }}
        >
          <div style={{ fontSize: '0.72rem', color: '#38bdf8', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '3px' }}>
            <span>📝 Exact Text Payload ({String(request.parameters.text).length} chars):</span>
          </div>
          <div
            style={{
              fontFamily: 'monospace',
              fontSize: '0.75rem',
              color: '#f8fafc',
              background: 'rgba(15, 23, 42, 0.75)',
              padding: '6px 8px',
              borderRadius: '4px',
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-all',
              maxHeight: '80px',
              overflowY: 'auto',
              border: '1px solid rgba(255, 255, 255, 0.08)',
            }}
          >
            {request.parameters.text || <em style={{ color: '#94a3b8' }}>(empty string)</em>}
          </div>
        </div>
      )}

      {/* Visual Grounded Target & Spatial Resolution Details */}
      <div className="approval-bubble-meta">
        Target Tool: <code>{request.toolName}</code>
        {request.parameters?.target_description && (
          <div className="approval-target-pill" style={{ marginTop: '4px', fontSize: '0.76rem', color: '#00e5ff' }}>
            🎯 Target: <strong>{request.parameters.target_description}</strong>
            {request.parameters.text && (
              <span style={{ marginLeft: '6px', color: '#f59e0b' }}>
                (Text: "{request.parameters.text}")
              </span>
            )}
          </div>
        )}

        {/* Resolved Click Coordinates, Bounding Box, and Detection Pipeline */}
        {(coordsDisplay || methodLabel) && (
          <div
            className="approval-coords-box"
            style={{
              display: 'flex',
              flexWrap: 'wrap',
              gap: '6px',
              alignItems: 'center',
              marginTop: '5px',
              padding: '4px 8px',
              background: 'rgba(15, 23, 42, 0.6)',
              borderRadius: '4px',
              border: '1px solid rgba(56, 189, 248, 0.2)',
              fontSize: '0.72rem',
            }}
          >
            {coordsDisplay && (
              <span style={{ color: '#38bdf8' }}>
                📍 Coords: <strong style={{ color: '#ffffff' }}>{coordsDisplay}</strong>
              </span>
            )}
            {bboxDisplay && (
              <span style={{ color: '#94a3b8', fontSize: '0.68rem' }}>
                Box: [{bboxDisplay}]
              </span>
            )}
            {methodLabel && (
              <span
                style={{
                  background: 'rgba(56, 189, 248, 0.15)',
                  color: '#7dd3fc',
                  padding: '1px 6px',
                  borderRadius: '3px',
                  fontSize: '0.67rem',
                  fontWeight: 600,
                }}
              >
                {methodLabel}
              </span>
            )}
            {confidenceDisplay && (
              <span style={{ color: '#a7f3d0', fontSize: '0.67rem' }}>
                ({confidenceDisplay})
              </span>
            )}
          </div>
        )}
      </div>

      {/* Focus Awareness Guard Notice */}
      {isShortcutOrInteraction && (
        <div
          style={{
            fontSize: '0.68rem',
            color: '#94a3b8',
            marginBottom: '8px',
            fontStyle: 'italic',
            display: 'flex',
            alignItems: 'center',
            gap: '4px',
          }}
        >
          <span>🛡️</span>
          <span>Focus Safety Guard: Approving automatically restores and activates the target window before input dispatch.</span>
        </div>
      )}

      <div className="approval-bubble-actions">
        {status === 'pending' ? (
          <>
            <button
              type="button"
              className="approval-btn approve"
              onClick={handleApproveClick}
              disabled={loading}
              title="Authorize this action immediately (Global Shortcut: Ctrl + Alt + Y)"
            >
              {loading ? 'AUTHORIZING...' : '✓ APPROVE'}
              <span
                style={{
                  marginLeft: '6px',
                  fontSize: '0.65rem',
                  opacity: 0.85,
                  padding: '1px 5px',
                  borderRadius: '3px',
                  background: 'rgba(0,0,0,0.3)',
                  border: '1px solid rgba(255,255,255,0.2)',
                  fontFamily: 'monospace',
                }}
              >
                Ctrl+Alt+Y
              </span>
            </button>
            <button
              type="button"
              className="approval-btn decline"
              onClick={handleDeclineClick}
              disabled={loading}
              title="Decline and block this action (Global Shortcut: Ctrl + Alt + N)"
            >
              {loading ? 'DECLINING...' : '✕ DECLINE'}
              <span
                style={{
                  marginLeft: '6px',
                  fontSize: '0.65rem',
                  opacity: 0.85,
                  padding: '1px 5px',
                  borderRadius: '3px',
                  background: 'rgba(0,0,0,0.3)',
                  border: '1px solid rgba(255,255,255,0.2)',
                  fontFamily: 'monospace',
                }}
              >
                Ctrl+Alt+N
              </span>
            </button>
          </>
        ) : status === 'approved' ? (
          <span className="approval-resolved-status approved">
            ✓ AUTHORIZATION GRANTED
          </span>
        ) : (
          <span className="approval-resolved-status rejected">
            ✕ AUTHORIZATION DECLINED
          </span>
        )}
      </div>
    </div>
  );
};
