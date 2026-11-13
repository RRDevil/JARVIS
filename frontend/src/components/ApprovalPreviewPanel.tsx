import React, { useState, useEffect, useCallback } from 'react';
import { ApprovalRequest } from '../types/contracts';
import { soundManager } from '../services/soundManager';
import { fetchPendingApprovals, respondToApproval, proposeToolExecution } from '../services/api';

interface ApprovalPreviewPanelProps {
  onRequestApprovalState?: () => void;
  onClearApprovalState?: () => void;
}

export const ApprovalPreviewPanel: React.FC<ApprovalPreviewPanelProps> = ({
  onRequestApprovalState,
  onClearApprovalState,
}) => {
  const [currentRequest, setCurrentRequest] = useState<ApprovalRequest | null>(null);
  const [isLiveBackend, setIsLiveBackend] = useState<boolean>(false);
  const [isProcessing, setIsProcessing] = useState<boolean>(false);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);

  // Poll for live pending approvals from FastAPI backend
  const checkPendingApprovals = useCallback(async () => {
    try {
      const pending = await fetchPendingApprovals();
      if (pending && pending.length > 0) {
        const latest = pending[0];
        setCurrentRequest(latest);
        setIsLiveBackend(true);
        if (onRequestApprovalState) onRequestApprovalState();
      } else if (isLiveBackend && currentRequest && currentRequest.status === 'pending') {
        // If live request was resolved on backend
        setCurrentRequest(null);
        if (onClearApprovalState) onClearApprovalState();
      }
    } catch {
      // Backend may be offline or during initial boot; keep demo mode operational
    }
  }, [isLiveBackend, currentRequest, onRequestApprovalState, onClearApprovalState]);

  useEffect(() => {
    checkPendingApprovals();
    const interval = setInterval(checkPendingApprovals, 3000);
    return () => clearInterval(interval);
  }, [checkPendingApprovals]);

  const handleApprove = async () => {
    if (!currentRequest) return;
    setIsProcessing(true);
    soundManager.play('ACTIVATION');

    if (isLiveBackend) {
      try {
        const res = await respondToApproval(currentRequest.id, true);
        setCurrentRequest(res.approval);
        setStatusMessage('Action authorized and executed successfully.');
      } catch (err: any) {
        setStatusMessage(`Approval failed: ${err.message}`);
      } finally {
        setIsProcessing(false);
        if (onClearApprovalState) onClearApprovalState();
      }
    } else {
      setCurrentRequest({ ...currentRequest, status: 'approved' });
      setIsProcessing(false);
      if (onClearApprovalState) onClearApprovalState();
    }
  };

  const handleReject = async () => {
    if (!currentRequest) return;
    setIsProcessing(true);
    soundManager.play('ERROR_OCCURRED');

    if (isLiveBackend) {
      try {
        const res = await respondToApproval(currentRequest.id, false);
        setCurrentRequest(res.approval);
        setStatusMessage('Action authorization was rejected.');
      } catch (err: any) {
        setStatusMessage(`Rejection failed: ${err.message}`);
      } finally {
        setIsProcessing(false);
        if (onClearApprovalState) onClearApprovalState();
      }
    } else {
      setCurrentRequest({ ...currentRequest, status: 'rejected' });
      setIsProcessing(false);
      if (onClearApprovalState) onClearApprovalState();
    }
  };

  const handleTriggerBackendProposal = async () => {
    setIsProcessing(true);
    setStatusMessage(null);
    soundManager.play('APPROVAL_REQUIRED');

    try {
      const res = await proposeToolExecution('windows_close_window', {
        handle: 1003,
        window_title: 'Untitled - Notepad',
      });
      if (res.approval_request) {
        setCurrentRequest(res.approval_request);
        setIsLiveBackend(true);
        if (onRequestApprovalState) onRequestApprovalState();
      }
    } catch (err: any) {
      // Fallback to local demo if backend is offline
      handleResetDemo();
    } finally {
      setIsProcessing(false);
    }
  };

  const handleResetDemo = () => {
    setIsLiveBackend(false);
    setStatusMessage(null);
    soundManager.play('APPROVAL_REQUIRED');
    setCurrentRequest({
      id: `req-preview-${Date.now().toString().slice(-4)}`,
      toolExecutionId: `exec-win-close-${Date.now().toString().slice(-3)}`,
      actionSummary: 'Close desktop window [1003] (Untitled - Notepad)',
      toolName: 'windows_close_window',
      riskTier: 'CONSEQUENTIAL',
      parameters: {
        handle: 1003,
        window_title: 'Untitled - Notepad',
      },
      requestedAt: new Date().toLocaleTimeString(),
      expiresAt: new Date(Date.now() + 300000).toLocaleTimeString(),
      status: 'pending',
    });
    if (onRequestApprovalState) onRequestApprovalState();
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.65rem' }}>
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
        <span>SECURITY GATEWAY</span>
        <span
          className="preview-watermark"
          style={{
            borderColor: isLiveBackend ? '#10b981' : undefined,
            color: isLiveBackend ? '#10b981' : undefined,
          }}
        >
          {isLiveBackend ? 'LIVE GATEWAY' : 'PHASE 3 ACTIVE'}
        </span>
      </div>

      {!currentRequest ? (
        <div style={{ textAlign: 'center', padding: '1rem', color: 'var(--hud-text-muted)', fontSize: '0.8rem' }}>
          <p>No authorization requests pending.</p>
          <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'center', marginTop: '0.6rem' }}>
            <button
              className="hud-btn"
              style={{ fontSize: '0.7rem' }}
              onClick={handleTriggerBackendProposal}
              disabled={isProcessing}
            >
              Propose Action
            </button>
            <button
              className="hud-btn secondary"
              style={{ fontSize: '0.7rem' }}
              onClick={handleResetDemo}
              disabled={isProcessing}
            >
              Simulate Demo
            </button>
          </div>
        </div>
      ) : (
        <div
          style={{
            padding: '0.7rem',
            background: 'rgba(0, 0, 0, 0.45)',
            border: `1px solid ${
              currentRequest.status === 'pending'
                ? '#f59e0b'
                : currentRequest.status === 'approved'
                ? '#10b981'
                : '#ef4444'
            }`,
            borderRadius: '3px',
            fontFamily: 'var(--hud-font-mono)',
            fontSize: '0.75rem',
            display: 'flex',
            flexDirection: 'column',
            gap: '0.45rem',
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ color: '#f59e0b', fontWeight: 700 }}>
              [{currentRequest.riskTier}]
            </span>
            <span style={{ color: 'var(--hud-text-muted)', fontSize: '0.7rem' }}>
              ID: {currentRequest.id}
            </span>
          </div>

          <div style={{ color: '#fff', fontWeight: 600 }}>{currentRequest.actionSummary}</div>

          <div
            style={{
              padding: '0.35rem 0.5rem',
              background: 'rgba(0, 0, 0, 0.4)',
              borderRadius: '2px',
              color: 'var(--hud-text-muted)',
              fontSize: '0.7rem',
            }}
          >
            <div>Tool: {currentRequest.toolName}</div>
            <div>Params: {JSON.stringify(currentRequest.parameters)}</div>
          </div>

          {statusMessage && (
            <div style={{ color: 'var(--hud-primary)', fontSize: '0.7rem' }}>
              {statusMessage}
            </div>
          )}

          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '0.2rem' }}>
            <span style={{ fontSize: '0.7rem', color: 'var(--hud-text-muted)' }}>
              Status:{' '}
              <strong
                style={{
                  textTransform: 'uppercase',
                  color:
                    currentRequest.status === 'approved'
                      ? '#34d399'
                      : currentRequest.status === 'rejected'
                      ? '#f87171'
                      : '#fbbf24',
                }}
              >
                {currentRequest.status}
              </strong>
            </span>

            {currentRequest.status === 'pending' ? (
              <div style={{ display: 'flex', gap: '0.35rem' }}>
                <button
                  className="hud-btn danger"
                  style={{ padding: '0.25rem 0.55rem', fontSize: '0.7rem' }}
                  onClick={handleReject}
                  disabled={isProcessing}
                >
                  REJECT
                </button>
                <button
                  className="hud-btn"
                  style={{ padding: '0.25rem 0.65rem', fontSize: '0.7rem' }}
                  onClick={handleApprove}
                  disabled={isProcessing}
                >
                  APPROVE
                </button>
              </div>
            ) : (
              <div style={{ display: 'flex', gap: '0.35rem' }}>
                <button
                  className="hud-btn secondary"
                  style={{ padding: '0.25rem 0.55rem', fontSize: '0.7rem' }}
                  onClick={() => setCurrentRequest(null)}
                >
                  Dismiss
                </button>
                <button
                  className="hud-btn"
                  style={{ padding: '0.25rem 0.55rem', fontSize: '0.7rem' }}
                  onClick={handleTriggerBackendProposal}
                >
                  New Request
                </button>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
