import React from 'react';
import { AssistantState, isValidStateTransition } from '../types/assistantState';
import { soundManager } from '../services/soundManager';

interface DevStateSimulatorProps {
  currentState: AssistantState;
  onStateChange: (newState: AssistantState) => void;
}

const ALL_STATES: AssistantState[] = [
  'IDLE',
  'LISTENING',
  'THINKING',
  'RESPONDING',
  'EXECUTING',
  'AWAITING_APPROVAL',
  'ERROR',
];

export const DevStateSimulator: React.FC<DevStateSimulatorProps> = ({
  currentState,
  onStateChange,
}) => {
  const handleSelectState = (state: AssistantState) => {
    if (state === currentState) return;

    // Validate transition
    if (!isValidStateTransition(currentState, state)) {
      console.warn(`[DEV SIMULATOR] Transition from ${currentState} to ${state} is non-standard, but permitted in dev simulation.`);
    }

    // Play appropriate sound cue
    switch (state) {
      case 'LISTENING':
        soundManager.play('LISTENING_START');
        break;
      case 'THINKING':
        soundManager.play('ACTIVATION');
        break;
      case 'RESPONDING':
        soundManager.play('RESPONSE_START');
        break;
      case 'AWAITING_APPROVAL':
        soundManager.play('APPROVAL_REQUIRED');
        break;
      case 'ERROR':
        soundManager.play('ERROR_OCCURRED');
        break;
      case 'IDLE':
        soundManager.play('RESPONSE_COMPLETE');
        break;
      case 'EXECUTING':
        soundManager.play('CLICK_CUE');
        break;
    }

    onStateChange(state);
  };

  return (
    <div className="dev-simulator-bar">
      <div className="simulator-header">
        <span>[DEVELOPMENT STATE PREVIEW]</span>
        <span style={{ color: '#f59e0b' }}>SIMULATED STATES // ZERO REAL AI/SYSTEM ACTIONS</span>
      </div>

      <div className="simulator-buttons">
        {ALL_STATES.map((st) => (
          <button
            key={st}
            className={`sim-btn ${st === currentState ? 'active' : ''}`}
            onClick={() => handleSelectState(st)}
            title={`Preview visual & audio feedback for ${st}`}
          >
            {st}
          </button>
        ))}
      </div>
    </div>
  );
};

