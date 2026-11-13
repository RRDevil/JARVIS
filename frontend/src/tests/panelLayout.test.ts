import { describe, it, expect } from 'vitest';
import { DEFAULT_SETTINGS, PanelId } from '../types/settings';

describe('Modular Panel Layout Logic', () => {
  it('contains all required core and preview panels in default layout', () => {
    const requiredPanels: PanelId[] = [
      'diagnostics',
      'systemMetrics',
      'activityLog',
      'conversationPreview',
      'approvalPreview',
    ];

    requiredPanels.forEach((id) => {
      const panel = DEFAULT_SETTINGS.panels[id];
      expect(panel).toBeDefined();
      expect(panel.id).toBe(id);
      expect(panel.visible).toBe(true);
      expect(panel.minimized).toBe(false);
      expect(typeof panel.order).toBe('number');
    });
  });

  it('orders panels monotonically by order index', () => {
    const sorted = (Object.keys(DEFAULT_SETTINGS.panels) as PanelId[]).sort(
      (a, b) => DEFAULT_SETTINGS.panels[a].order - DEFAULT_SETTINGS.panels[b].order
    );

    for (let i = 0; i < sorted.length - 1; i++) {
      expect(DEFAULT_SETTINGS.panels[sorted[i]].order).toBeLessThanOrEqual(
        DEFAULT_SETTINGS.panels[sorted[i + 1]].order
      );
    }
  });
});

