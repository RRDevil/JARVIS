import { describe, it, expect } from 'vitest';

/**
 * Mathematical WCAG 2.1 Luminance and Contrast Ratio calculation
 */
function sRgbToLinear(c: number): number {
  const norm = c / 255;
  return norm <= 0.03928 ? norm / 12.92 : Math.pow((norm + 0.055) / 1.055, 2.4);
}

function getRelativeLuminance(r: number, g: number, b: number): number {
  return 0.2126 * sRgbToLinear(r) + 0.7152 * sRgbToLinear(g) + 0.0722 * sRgbToLinear(b);
}

function getContrastRatio(l1: number, l2: number): number {
  const lighter = Math.max(l1, l2);
  const darker = Math.min(l1, l2);
  return (lighter + 0.05) / (darker + 0.05);
}

function blendColor(
  fg: [number, number, number],
  alpha: number,
  bg: [number, number, number]
): [number, number, number] {
  return [
    Math.round(fg[0] * alpha + bg[0] * (1 - alpha)),
    Math.round(fg[1] * alpha + bg[1] * (1 - alpha)),
    Math.round(fg[2] * alpha + bg[2] * (1 - alpha)),
  ];
}

describe('Chat Readability & Surface Contrast Verification across Desktop Backgrounds', () => {
  // JARVIS Chat Palette
  const ASSISTANT_SURFACE: [number, number, number] = [9, 15, 24]; // rgba(9, 15, 24, 0.92)
  const USER_SURFACE: [number, number, number] = [15, 23, 38]; // rgba(15, 23, 38, 0.92)
  const SURFACE_ALPHA = 0.92;

  const TEXT_PRIMARY: [number, number, number] = [241, 243, 245]; // #F1F3F5
  const TEXT_SECONDARY: [number, number, number] = [176, 183, 195]; // #B0B7C3
  const TEXT_MUTED: [number, number, number] = [137, 147, 163]; // #8993A3
  const ACCENT_CYAN: [number, number, number] = [0, 229, 255]; // #00e5ff

  // 5 Real-World Background Scenarios
  const TEST_BACKGROUNDS: Record<string, [number, number, number]> = {
    '1. Pure White (#FFFFFF - Notepad, Blank Webpage, Word)': [255, 255, 255],
    '2. Pure Black (#000000 - Dark Wallpaper, Terminal, OLED)': [0, 0, 0],
    '3. Colorful Vibrant Wallpaper (#E11D48 - Crimson Accent)': [225, 29, 72],
    '4. Bright Application Window (#F8FAFC - File Explorer)': [248, 250, 252],
    '5. Dark Application Window (#1E293B - VS Code / Dark HUD)': [30, 41, 59],
  };

  for (const [bgName, bgRgb] of Object.entries(TEST_BACKGROUNDS)) {
    describe(`Scenario: ${bgName}`, () => {
      it('guarantees Primary Text exceeds WCAG AAA (7.0:1) on Assistant bubble', () => {
        const effectiveBg = blendColor(ASSISTANT_SURFACE, SURFACE_ALPHA, bgRgb);
        const lBg = getRelativeLuminance(...effectiveBg);
        const lText = getRelativeLuminance(...TEXT_PRIMARY);
        const contrast = getContrastRatio(lText, lBg);

        // WCAG AAA requires >= 7.0:1
        expect(contrast).toBeGreaterThanOrEqual(7.0);
        expect(contrast).toBeGreaterThan(12.0); // Typically 13:1 to 17:1
      });

      it('guarantees Primary Text exceeds WCAG AAA (7.0:1) on User bubble', () => {
        const effectiveBg = blendColor(USER_SURFACE, SURFACE_ALPHA, bgRgb);
        const lBg = getRelativeLuminance(...effectiveBg);
        const lText = getRelativeLuminance(...TEXT_PRIMARY);
        const contrast = getContrastRatio(lText, lBg);

        expect(contrast).toBeGreaterThanOrEqual(7.0);
        expect(contrast).toBeGreaterThan(12.0);
      });

      it('guarantees Secondary Text exceeds WCAG AAA (7.0:1) on Assistant bubble', () => {
        const effectiveBg = blendColor(ASSISTANT_SURFACE, SURFACE_ALPHA, bgRgb);
        const lBg = getRelativeLuminance(...effectiveBg);
        const lText = getRelativeLuminance(...TEXT_SECONDARY);
        const contrast = getContrastRatio(lText, lBg);

        expect(contrast).toBeGreaterThanOrEqual(7.0);
      });

      it('guarantees Muted Metadata exceeds WCAG AA (4.5:1) on Assistant bubble', () => {
        const effectiveBg = blendColor(ASSISTANT_SURFACE, SURFACE_ALPHA, bgRgb);
        const lBg = getRelativeLuminance(...effectiveBg);
        const lText = getRelativeLuminance(...TEXT_MUTED);
        const contrast = getContrastRatio(lText, lBg);

        expect(contrast).toBeGreaterThanOrEqual(4.5);
      });

      it('guarantees Accent Cyan interactive elements exceed WCAG AAA (7.0:1)', () => {
        const effectiveBg = blendColor(ASSISTANT_SURFACE, SURFACE_ALPHA, bgRgb);
        const lBg = getRelativeLuminance(...effectiveBg);
        const lText = getRelativeLuminance(...ACCENT_CYAN);
        const contrast = getContrastRatio(lText, lBg);

        expect(contrast).toBeGreaterThanOrEqual(7.0);
      });
    });
  }
});

