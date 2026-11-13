import React from 'react';
import { AssistantState, ASSISTANT_STATE_META } from '../types/assistantState';
import { PerceptionStage } from '../types/contracts';
import { soundManager } from '../services/soundManager';

interface ArcReactorProps {
  assistantState: AssistantState;
  latencyMs: number | null;
  onActivate?: () => void;
  perceptionStage?: PerceptionStage;
  onStopSpeaking?: () => void;
  onClearError?: () => void;
}

export const ArcReactor: React.FC<ArcReactorProps> = ({
  assistantState,
  latencyMs,
  onActivate,
  perceptionStage,
  onStopSpeaking,
  onClearError,
}) => {
  const meta = ASSISTANT_STATE_META[assistantState] || ASSISTANT_STATE_META.IDLE;

  const handleClick = () => {
    if (assistantState === 'SPEAKING' && onStopSpeaking) {
      onStopSpeaking();
      return;
    }
    if (assistantState === 'ERROR' && onClearError) {
      onClearError();
      return;
    }
    soundManager.play('ACTIVATION');
    if (onActivate) onActivate();
  };

  const getRotationClass = () => {
    if (perceptionStage && perceptionStage !== 'IDLE') {
      return 'rot-fast';
    }
    switch (meta.ringRotationSpeed) {
      case 'fast':
        return 'rot-fast';
      case 'reverse':
        return 'rot-reverse';
      case 'static':
        return 'rot-static';
      case 'normal':
      default:
        return 'rot-normal';
    }
  };

  const getPulseClass = () => {
    if (perceptionStage && perceptionStage !== 'IDLE') {
      return 'pulse-fast';
    }
    switch (meta.pulseRate) {
      case 'fast':
        return 'pulse-fast';
      case 'urgent':
        return 'pulse-urgent';
      case 'medium':
        return 'pulse-medium';
      case 'slow':
      default:
        return 'pulse-slow';
    }
  };

  const getCoreLabel = () => {
    if (perceptionStage && perceptionStage !== 'IDLE') {
      switch (perceptionStage) {
        case 'CAPTURING':
          return 'CAPTURE';
        case 'READING_OCR':
          return 'READ OCR';
        case 'ANALYZING_VISION':
          return 'VISION AI';
        case 'GENERATING':
          return 'SPEAKING';
        case 'COMPLETED':
          return 'DONE';
        case 'FAILED':
          return 'FAULT';
        case 'CANCELLED':
          return 'HALTED';
      }
    }
    switch (assistantState) {
      case 'AWAITING_APPROVAL':
        return 'APPROVAL';
      case 'RESPONDING':
        return 'STREAMING';
      case 'SPEAKING':
        return 'SPEAKING';
      default:
        return assistantState;
    }
  };

  return (
    <div
      className="arc-reactor-wrapper"
      onClick={handleClick}
      role="button"
      tabIndex={0}
      aria-label={`JARVIS Arc Core: ${meta.label}. Click to activate.`}
      title={`${meta.label} - ${meta.description} (Latency: ${latencyMs ?? '--'}ms)`}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          handleClick();
        }
      }}
    >
      <div
        className={`arc-outer-ring ${getRotationClass()}`}
        style={{ borderColor: meta.color }}
      />
      <div
        className={`arc-middle-ring ${getRotationClass()}`}
        style={{
          borderTopColor: meta.color,
          borderBottomColor: meta.color,
        }}
      />
      <div
        className={`arc-inner-ring ${getPulseClass()}`}
        style={{
          borderColor: meta.color,
          boxShadow: `0 0 25px ${meta.glowColor}`,
        }}
      />
      <div
        className="arc-core-icon"
        style={{
          color: '#fff',
          textShadow: `0 0 10px ${meta.color}`,
        }}
      >
        <span>{getCoreLabel()}</span>
      </div>
    </div>
  );
};
