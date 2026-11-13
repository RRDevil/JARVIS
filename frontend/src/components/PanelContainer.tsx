import React, { ReactNode } from 'react';
import { PanelConfig } from '../types/settings';
import { soundManager } from '../services/soundManager';

interface PanelContainerProps {
  config: PanelConfig;
  onToggleMinimize: (id: string) => void;
  onToggleVisibility: (id: string) => void;
  onMoveOrder: (id: string, delta: number) => void;
  canMoveUp?: boolean;
  canMoveDown?: boolean;
  badge?: ReactNode;
  children: ReactNode;
}

export const PanelContainer: React.FC<PanelContainerProps> = ({
  config,
  onToggleMinimize,
  onToggleVisibility,
  onMoveOrder,
  canMoveUp = false,
  canMoveDown = false,
  badge,
  children,
}) => {
  if (!config.visible) return null;

  const handleMinimize = (e: React.MouseEvent) => {
    e.stopPropagation();
    soundManager.play('CLICK_CUE');
    onToggleMinimize(config.id);
  };

  const handleClose = (e: React.MouseEvent) => {
    e.stopPropagation();
    soundManager.play('CLICK_CUE');
    onToggleVisibility(config.id);
  };

  const handleMove = (e: React.MouseEvent, delta: number) => {
    e.stopPropagation();
    soundManager.play('CLICK_CUE');
    onMoveOrder(config.id, delta);
  };

  return (
    <section className="hud-panel" aria-label={config.title}>
      <header className="panel-header-bar">
        <div className="panel-title-text">
          <span>{config.title}</span>
          {badge}
        </div>

        <div className="panel-actions">
          {canMoveUp && (
            <button
              className="panel-icon-btn"
              onClick={(e) => handleMove(e, -1)}
              title="Move Panel Up / Previous"
              aria-label={`Move ${config.title} up`}
            >
              ▲
            </button>
          )}

          {canMoveDown && (
            <button
              className="panel-icon-btn"
              onClick={(e) => handleMove(e, 1)}
              title="Move Panel Down / Next"
              aria-label={`Move ${config.title} down`}
            >
              ▼
            </button>
          )}

          <button
            className="panel-icon-btn"
            onClick={handleMinimize}
            title={config.minimized ? 'Restore Panel' : 'Minimize Panel'}
            aria-label={config.minimized ? 'Restore panel' : 'Minimize panel'}
          >
            {config.minimized ? '□' : '_'}
          </button>

          <button
            className="panel-icon-btn"
            onClick={handleClose}
            title="Hide Panel (Restore in Settings)"
            aria-label={`Hide ${config.title}`}
          >
            ✕
          </button>
        </div>
      </header>

      {!config.minimized && <div className="panel-body">{children}</div>}
    </section>
  );
};

