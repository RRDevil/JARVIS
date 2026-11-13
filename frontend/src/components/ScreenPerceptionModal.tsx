import React, { useState, useEffect } from 'react';
import { GroundedUIElement, MonitorInfo, PerceptionProgress } from '../types/contracts';
import { fetchMonitors, locateScreenElements } from '../services/api';
import { soundManager } from '../services/soundManager';

interface ScreenPerceptionModalProps {
  isOpen: boolean;
  onClose: () => void;
  onPerformPerception: (
    analysisMode: 'ocr_only' | 'gemini_vision',
    monitorId: number,
    activeWindowOnly: boolean,
    userQueryPrompt?: string
  ) => Promise<void>;
  isProcessing?: boolean;
  perceptionProgress?: PerceptionProgress;
  onCancelPerception?: () => void;
}

export const ScreenPerceptionModal: React.FC<ScreenPerceptionModalProps> = ({
  isOpen,
  onClose,
  onPerformPerception,
  isProcessing = false,
  perceptionProgress,
  onCancelPerception,
}) => {
  const [monitors, setMonitors] = useState<MonitorInfo[]>([]);
  const [selectedMonitor, setSelectedMonitor] = useState<number>(1);
  const [activeWindowOnly, setActiveWindowOnly] = useState<boolean>(true);
  const [userPrompt, setUserPrompt] = useState<string>('What is currently displayed on my screen?');
  const [step, setStep] = useState<'configure' | 'consent_warning' | 'view_elements'>('configure');
  const [groundedElements, setGroundedElements] = useState<GroundedUIElement[]>([]);
  const [locatingElements, setLocatingElements] = useState<boolean>(false);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);

  const isActivelyPerceiving = Boolean(
    isProcessing || (perceptionProgress && perceptionProgress.stage !== 'IDLE')
  );

  useEffect(() => {
    if (isOpen) {
      soundManager.play('ACTIVATION');
      setStep('configure');
      setStatusMessage(null);
      fetchMonitors()
        .then((mons) => {
          setMonitors(mons);
          const primary = mons.find((m) => m.is_primary && m.monitor_id > 0);
          if (primary) setSelectedMonitor(primary.monitor_id);
          else if (mons.length > 1) setSelectedMonitor(1);
          else if (mons.length > 0) setSelectedMonitor(mons[0].monitor_id);
        })
        .catch(() => {
          // Fallback primary display
          setMonitors([
            {
              monitor_id: 1,
              name: 'Primary Desktop Monitor',
              left: 0,
              top: 0,
              width: 1920,
              height: 1080,
              is_primary: true,
            },
          ]);
        });
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const handleStartOCR = async () => {
    soundManager.play('CLICK_CUE');
    try {
      await onPerformPerception('ocr_only', selectedMonitor, activeWindowOnly, 'Read the text in this window.');
      onClose();
    } catch (err: any) {
      setStatusMessage(`Error: ${err.message}`);
    }
  };

  const handleStartVision = async () => {
    soundManager.play('CLICK_CUE');
    try {
      await onPerformPerception('gemini_vision', selectedMonitor, activeWindowOnly, userPrompt);
      onClose();
    } catch (err: any) {
      setStatusMessage(`Error: ${err.message}`);
    }
  };

  const handleLocateElements = async () => {
    soundManager.play('CLICK_CUE');
    setLocatingElements(true);
    setStatusMessage(null);
    try {
      const res = await locateScreenElements({
        monitor_id: selectedMonitor,
        active_window_only: activeWindowOnly,
      });
      setGroundedElements(res.elements);
      setStep('view_elements');
    } catch (err: any) {
      setStatusMessage(`Grounding failed: ${err.message}`);
    } finally {
      setLocatingElements(false);
    }
  };

  return (
    <div className="jarvis-modal-backdrop" onClick={onClose}>
      <div
        className="jarvis-screen-perception-modal"
        onClick={(e) => e.stopPropagation()}
        style={{
          background: 'rgba(6, 18, 38, 0.95)',
          backdropFilter: 'blur(24px)',
          WebkitBackdropFilter: 'blur(24px)',
          border: '1px solid rgba(0, 229, 255, 0.4)',
          boxShadow: '0 12px 40px rgba(0, 0, 0, 0.8), 0 0 30px rgba(0, 229, 255, 0.15)',
          borderRadius: '8px',
          padding: '1.25rem 1.5rem',
          maxWidth: '480px',
          width: '92%',
          color: 'var(--hud-text)',
          fontFamily: 'var(--hud-font-hud)',
          position: 'relative',
          animation: 'bubble-pop-in 0.25s cubic-bezier(0.34, 1.56, 0.64, 1) forwards',
        }}
      >
        {/* Header */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem', borderBottom: '1px solid rgba(0, 229, 255, 0.2)', paddingBottom: '0.6rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span
              style={{
                width: '8px',
                height: '8px',
                borderRadius: '50%',
                background: isActivelyPerceiving ? '#f59e0b' : 'var(--hud-primary)',
                boxShadow: isActivelyPerceiving ? '0 0 10px #f59e0b' : '0 0 8px var(--hud-primary)',
              }}
            />
            <span style={{ fontSize: '0.88rem', letterSpacing: '0.12em', color: 'var(--hud-primary)', fontWeight: 800 }}>
              VISION PROTOCOL // SCREEN PERCEPTION
            </span>
          </div>
          <button
            type="button"
            onClick={onClose}
            style={{
              background: 'transparent',
              border: 'none',
              color: 'var(--hud-text-muted)',
              cursor: 'pointer',
              fontSize: '1rem',
            }}
          >
            ✕
          </button>
        </div>

        {/* Real-time Active Processing Lifecycle Display */}
        {isActivelyPerceiving && perceptionProgress && perceptionProgress.stage !== 'IDLE' ? (
          <div style={{ padding: '0.5rem 0' }}>
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '0.75rem 1rem',
                background: 'rgba(0, 229, 255, 0.08)',
                border: '1px solid rgba(0, 229, 255, 0.35)',
                borderRadius: '6px',
                marginBottom: '1rem',
              }}
            >
              <div>
                <div style={{ fontSize: '0.65rem', color: 'var(--hud-text-muted)', letterSpacing: '0.1em' }}>
                  ACTIVE STAGE // {perceptionProgress.targetDescription}
                </div>
                <div style={{ fontSize: '0.88rem', color: '#00e5ff', fontWeight: 800, marginTop: '2px', letterSpacing: '0.08em' }}>
                  {perceptionProgress.stageMessage}
                </div>
              </div>
              <div className="status-dot-pulse" style={{ background: '#00e5ff' }} />
            </div>

            {/* Stepper Progress */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '6px', marginBottom: '1.25rem' }}>
              {[
                { key: 'CAPTURING', label: '1. CAPTURE' },
                { key: 'READING_OCR', label: '2. OCR' },
                { key: 'ANALYZING_VISION', label: '3. VISION' },
                { key: 'GENERATING', label: '4. OUTPUT' },
              ].map((s) => {
                const stageOrder = ['CAPTURING', 'READING_OCR', 'ANALYZING_VISION', 'GENERATING', 'COMPLETED'];
                const currentIdx = stageOrder.indexOf(perceptionProgress.stage);
                const itemIdx = stageOrder.indexOf(s.key);
                const isPassedOrActive = currentIdx >= itemIdx;
                const isCurrent = perceptionProgress.stage === s.key;

                return (
                  <div
                    key={s.key}
                    style={{
                      textAlign: 'center',
                      padding: '4px 2px',
                      fontSize: '0.62rem',
                      fontFamily: 'var(--hud-font-mono)',
                      borderRadius: '4px',
                      background: isCurrent
                        ? 'rgba(0, 229, 255, 0.25)'
                        : isPassedOrActive
                        ? 'rgba(16, 185, 129, 0.15)'
                        : 'rgba(255, 255, 255, 0.04)',
                      border: isCurrent
                        ? '1px solid #00e5ff'
                        : isPassedOrActive
                        ? '1px solid rgba(16, 185, 129, 0.4)'
                        : '1px solid rgba(255, 255, 255, 0.1)',
                      color: isCurrent ? '#00e5ff' : isPassedOrActive ? '#6ee7b7' : 'var(--hud-text-muted)',
                      fontWeight: isCurrent ? 800 : 500,
                    }}
                  >
                    {s.label}
                  </div>
                );
              })}
            </div>

            {/* Action Buttons while processing */}
            <div style={{ display: 'flex', gap: '8px' }}>
              {onCancelPerception && (
                <button
                  type="button"
                  onClick={onCancelPerception}
                  style={{
                    flex: 1,
                    padding: '0.6rem',
                    background: 'rgba(239, 68, 68, 0.15)',
                    border: '1px solid #ef4444',
                    borderRadius: '4px',
                    color: '#fca5a5',
                    fontSize: '0.75rem',
                    fontFamily: 'var(--hud-font-hud)',
                    fontWeight: 700,
                    cursor: 'pointer',
                  }}
                >
                  ✕ CANCEL OPERATION
                </button>
              )}
              <button
                type="button"
                onClick={onClose}
                style={{
                  flex: 1,
                  padding: '0.6rem',
                  background: 'rgba(0, 229, 255, 0.12)',
                  border: '1px solid var(--hud-primary)',
                  borderRadius: '4px',
                  color: 'var(--hud-primary)',
                  fontSize: '0.75rem',
                  fontFamily: 'var(--hud-font-hud)',
                  cursor: 'pointer',
                }}
              >
                VIEW STREAM IN HUD »
              </button>
            </div>
          </div>
        ) : step === 'configure' ? (
          <div>
            {/* Monitor Selection */}
            <div style={{ marginBottom: '1rem' }}>
              <label style={{ display: 'block', fontSize: '0.72rem', letterSpacing: '0.08em', color: 'var(--hud-text-muted)', marginBottom: '0.4rem' }}>
                TARGET DISPLAY MONITOR:
              </label>
              <select
                value={selectedMonitor}
                onChange={(e) => setSelectedMonitor(Number(e.target.value))}
                style={{
                  width: '100%',
                  background: 'rgba(0, 229, 255, 0.06)',
                  border: '1px solid rgba(0, 229, 255, 0.3)',
                  borderRadius: '4px',
                  color: '#e0f2fe',
                  padding: '0.45rem 0.6rem',
                  fontSize: '0.78rem',
                  fontFamily: 'var(--hud-font-mono)',
                  outline: 'none',
                }}
              >
                {monitors.map((m) => (
                  <option key={m.monitor_id} value={m.monitor_id} style={{ background: '#0a192f', color: '#e0f2fe' }}>
                    {m.name} ({m.width}x{m.height}) {m.is_primary ? '[PRIMARY]' : ''}
                  </option>
                ))}
              </select>
            </div>

            {/* Scope: Active Window vs Full Desktop */}
            <div style={{ marginBottom: '1.1rem' }}>
              <label style={{ display: 'block', fontSize: '0.72rem', letterSpacing: '0.08em', color: 'var(--hud-text-muted)', marginBottom: '0.4rem' }}>
                CAPTURE SCOPE:
              </label>
              <div style={{ display: 'flex', gap: '8px' }}>
                <button
                  type="button"
                  onClick={() => setActiveWindowOnly(true)}
                  style={{
                    flex: 1,
                    padding: '0.5rem',
                    borderRadius: '4px',
                    fontSize: '0.74rem',
                    fontFamily: 'var(--hud-font-hud)',
                    cursor: 'pointer',
                    border: activeWindowOnly ? '1px solid var(--hud-primary)' : '1px solid rgba(255,255,255,0.1)',
                    background: activeWindowOnly ? 'rgba(0, 229, 255, 0.18)' : 'rgba(255,255,255,0.03)',
                    color: activeWindowOnly ? 'var(--hud-primary)' : 'var(--hud-text-muted)',
                    transition: 'all 0.15s ease',
                  }}
                >
                  ⚡ Active Window Only (Private)
                </button>
                <button
                  type="button"
                  onClick={() => setActiveWindowOnly(false)}
                  style={{
                    flex: 1,
                    padding: '0.5rem',
                    borderRadius: '4px',
                    fontSize: '0.74rem',
                    fontFamily: 'var(--hud-font-hud)',
                    cursor: 'pointer',
                    border: !activeWindowOnly ? '1px solid var(--hud-primary)' : '1px solid rgba(255,255,255,0.1)',
                    background: !activeWindowOnly ? 'rgba(0, 229, 255, 0.18)' : 'rgba(255,255,255,0.03)',
                    color: !activeWindowOnly ? 'var(--hud-primary)' : 'var(--hud-text-muted)',
                    transition: 'all 0.15s ease',
                  }}
                >
                  🖥 Full Desktop Monitor
                </button>
              </div>
            </div>

            {/* Action Modes */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginTop: '1.25rem' }}>
              <button
                type="button"
                onClick={handleStartOCR}
                disabled={isProcessing}
                style={{
                  width: '100%',
                  padding: '0.65rem 1rem',
                  background: 'rgba(16, 185, 129, 0.15)',
                  border: '1px solid #10b981',
                  borderRadius: '4px',
                  color: '#a7f3d0',
                  fontFamily: 'var(--hud-font-hud)',
                  fontSize: '0.8rem',
                  fontWeight: 700,
                  cursor: isProcessing ? 'not-allowed' : 'pointer',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                }}
              >
                <span>📄 READ VISIBLE TEXT (LOCAL OCR)</span>
                <span style={{ fontSize: '0.65rem', opacity: 0.8 }}>100% On-Device</span>
              </button>

              <button
                type="button"
                onClick={() => setStep('consent_warning')}
                disabled={isProcessing}
                style={{
                  width: '100%',
                  padding: '0.65rem 1rem',
                  background: 'rgba(0, 229, 255, 0.15)',
                  border: '1px solid var(--hud-primary)',
                  borderRadius: '4px',
                  color: '#e0f2fe',
                  fontFamily: 'var(--hud-font-hud)',
                  fontSize: '0.8rem',
                  fontWeight: 700,
                  cursor: isProcessing ? 'not-allowed' : 'pointer',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                }}
              >
                <span>👁 MULTIMODAL VISION REASONING</span>
                <span style={{ fontSize: '0.65rem', opacity: 0.8 }}>Gemini Vision »</span>
              </button>

              <button
                type="button"
                onClick={handleLocateElements}
                disabled={isProcessing || locatingElements}
                style={{
                  width: '100%',
                  padding: '0.65rem 1rem',
                  background: 'rgba(245, 158, 11, 0.15)',
                  border: '1px solid #f59e0b',
                  borderRadius: '4px',
                  color: '#fef3c7',
                  fontFamily: 'var(--hud-font-hud)',
                  fontSize: '0.8rem',
                  fontWeight: 700,
                  cursor: isProcessing || locatingElements ? 'not-allowed' : 'pointer',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                }}
              >
                <span>🎯 GROUND INTERACTIVE UI CONTROLS</span>
                <span style={{ fontSize: '0.65rem', opacity: 0.8 }}>{locatingElements ? 'Scanning...' : 'Phase 5 Grounding »'}</span>
              </button>
            </div>
          </div>
        ) : step === 'view_elements' ? (
          /* Discovered Grounded UI Elements List */
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
              <span style={{ fontSize: '0.74rem', letterSpacing: '0.08em', color: 'var(--hud-primary)', fontWeight: 700 }}>
                GROUNDED INTERACTIVE CONTROLS ({groundedElements.length})
              </span>
              <button
                type="button"
                onClick={() => setStep('configure')}
                style={{
                  background: 'transparent',
                  border: '1px solid rgba(255, 255, 255, 0.2)',
                  borderRadius: '3px',
                  color: 'var(--hud-text-muted)',
                  fontSize: '0.7rem',
                  padding: '0.2rem 0.5rem',
                  cursor: 'pointer',
                }}
              >
                « BACK
              </button>
            </div>

            <div
              style={{
                maxHeight: '280px',
                overflowY: 'auto',
                display: 'flex',
                flexDirection: 'column',
                gap: '6px',
                paddingRight: '4px',
              }}
            >
              {groundedElements.length === 0 ? (
                <div style={{ padding: '1rem', textAlign: 'center', color: 'var(--hud-text-muted)', fontSize: '0.75rem' }}>
                  No interactive elements were recognized in the target window.
                </div>
              ) : (
                groundedElements.map((elem) => (
                  <div
                    key={elem.element_id}
                    style={{
                      background: 'rgba(0, 229, 255, 0.04)',
                      border: '1px solid rgba(0, 229, 255, 0.2)',
                      borderRadius: '4px',
                      padding: '0.45rem 0.6rem',
                      display: 'flex',
                      flexDirection: 'column',
                      gap: '2px',
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <span style={{ fontSize: '0.78rem', fontWeight: 700, color: '#e0f2fe' }}>
                        {elem.text || elem.description}
                      </span>
                      <span
                        style={{
                          fontSize: '0.62rem',
                          background: 'rgba(0, 229, 255, 0.15)',
                          color: 'var(--hud-primary)',
                          padding: '1px 5px',
                          borderRadius: '3px',
                          textTransform: 'uppercase',
                        }}
                      >
                        {elem.element_type}
                      </span>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.66rem', color: 'var(--hud-text-muted)' }}>
                      <span>Center: ({elem.center.x}, {elem.center.y}) | Bounds: {elem.bounding_box.width}x{elem.bounding_box.height}</span>
                      <span style={{ color: elem.source === 'hybrid' ? '#10b981' : '#f59e0b' }}>
                        {elem.source.toUpperCase()} ({(elem.confidence * 100).toFixed(0)}%)
                      </span>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        ) : (
          /* Consent Warning Screen */
          <div>
            <div
              style={{
                background: 'rgba(245, 158, 11, 0.12)',
                border: '1px solid #f59e0b',
                borderRadius: '4px',
                padding: '0.75rem 0.9rem',
                marginBottom: '1rem',
                color: '#fef3c7',
                fontSize: '0.76rem',
                lineHeight: '1.45',
              }}
            >
              <div style={{ fontWeight: 800, color: '#f59e0b', marginBottom: '0.35rem', display: 'flex', alignItems: 'center', gap: '6px' }}>
                <span>⚠</span>
                <span>EXTERNAL PROCESSING AUTHORIZATION</span>
              </div>
              <div>
                A high-resolution screenshot of your {activeWindowOnly ? 'active window' : `Display ${selectedMonitor}`} will be captured on-demand and transmitted to the Google Gemini API for visual reasoning.
              </div>
              <div style={{ marginTop: '0.4rem', fontSize: '0.7rem', color: '#fde68a' }}>
                • Images are ephemeral and not permanently stored.
                <br />• Screen content is never logged in plaintext audit files.
              </div>
            </div>

            <div style={{ marginBottom: '1rem' }}>
              <label style={{ display: 'block', fontSize: '0.72rem', letterSpacing: '0.08em', color: 'var(--hud-text-muted)', marginBottom: '0.4rem' }}>
                INSTRUCTION / QUERY FOR J.A.R.V.I.S.:
              </label>
              <input
                type="text"
                value={userPrompt}
                onChange={(e) => setUserPrompt(e.target.value)}
                placeholder="e.g. What is this error? / Explain this UI"
                style={{
                  width: '100%',
                  background: 'rgba(0, 229, 255, 0.06)',
                  border: '1px solid rgba(0, 229, 255, 0.3)',
                  borderRadius: '4px',
                  color: '#e0f2fe',
                  padding: '0.45rem 0.6rem',
                  fontSize: '0.8rem',
                  fontFamily: 'var(--hud-font-mono)',
                  boxSizing: 'border-box',
                }}
              />
            </div>

            <div style={{ display: 'flex', gap: '8px' }}>
              <button
                type="button"
                onClick={() => setStep('configure')}
                style={{
                  flex: 1,
                  padding: '0.6rem',
                  background: 'rgba(255, 255, 255, 0.05)',
                  border: '1px solid rgba(255, 255, 255, 0.2)',
                  borderRadius: '4px',
                  color: 'var(--hud-text-muted)',
                  fontSize: '0.75rem',
                  fontFamily: 'var(--hud-font-hud)',
                  cursor: 'pointer',
                }}
              >
                « BACK
              </button>
              <button
                type="button"
                onClick={handleStartVision}
                disabled={isProcessing}
                style={{
                  flex: 2,
                  padding: '0.6rem',
                  background: 'linear-gradient(135deg, rgba(0, 229, 255, 0.3), rgba(14, 165, 233, 0.5))',
                  border: '1px solid var(--hud-primary)',
                  borderRadius: '4px',
                  color: '#ffffff',
                  fontSize: '0.78rem',
                  fontFamily: 'var(--hud-font-hud)',
                  fontWeight: 800,
                  cursor: isProcessing ? 'not-allowed' : 'pointer',
                  boxShadow: '0 0 15px rgba(0, 229, 255, 0.3)',
                }}
              >
                {isProcessing ? 'ANALYZING...' : '✓ AUTHORIZE & INSPECT'}
              </button>
            </div>
          </div>
        )}

        {statusMessage && (
          <div
            style={{
              marginTop: '0.8rem',
              padding: '0.35rem 0.6rem',
              background: 'rgba(0, 229, 255, 0.08)',
              borderLeft: '2px solid var(--hud-primary)',
              borderRadius: '2px',
              fontFamily: 'var(--hud-font-mono)',
              fontSize: '0.68rem',
              color: 'var(--hud-primary)',
            }}
          >
            {statusMessage}
          </div>
        )}
      </div>
    </div>
  );
};
