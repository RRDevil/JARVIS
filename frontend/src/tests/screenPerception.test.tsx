import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { ScreenPerceptionModal } from '../components/ScreenPerceptionModal';
import * as api from '../services/api';

describe('ScreenPerceptionModal Component', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  const mockMonitors = [
    {
      monitor_id: 0,
      name: 'All Monitors (Combined Desktop)',
      left: 0,
      top: 0,
      width: 1920,
      height: 1080,
      is_primary: false,
    },
    {
      monitor_id: 1,
      name: 'Generic PnP Monitor',
      left: 0,
      top: 0,
      width: 1920,
      height: 1080,
      is_primary: true,
    },
  ];

  it('renders display monitors and mode options when opened', async () => {
    vi.spyOn(api, 'fetchMonitors').mockResolvedValue(mockMonitors);

    render(
      <ScreenPerceptionModal
        isOpen={true}
        onClose={vi.fn()}
        onPerformPerception={vi.fn()}
      />
    );

    expect(screen.getByText(/SCREEN PERCEPTION/i)).not.toBeNull();
    await waitFor(() => {
      expect(screen.getByText(/READ VISIBLE TEXT \(LOCAL OCR\)/i)).not.toBeNull();
      expect(screen.getByText(/MULTIMODAL VISION REASONING/i)).not.toBeNull();
    });
  });

  it('triggers local OCR on-device mode directly without external upload', async () => {
    vi.spyOn(api, 'fetchMonitors').mockResolvedValue(mockMonitors);
    const onPerceive = vi.fn().mockResolvedValue(undefined);
    const onClose = vi.fn();

    render(
      <ScreenPerceptionModal
        isOpen={true}
        onClose={onClose}
        onPerformPerception={onPerceive}
      />
    );

    await waitFor(() => {
      expect(screen.getByText(/READ VISIBLE TEXT \(LOCAL OCR\)/i)).not.toBeNull();
    });

    const ocrBtn = screen.getByText(/READ VISIBLE TEXT \(LOCAL OCR\)/i);
    fireEvent.click(ocrBtn);

    expect(onPerceive).toHaveBeenCalledWith(
      'ocr_only',
      1,
      true, // Default active window only
      expect.any(String)
    );
    await waitFor(() => {
      expect(onClose).toHaveBeenCalled();
    });
  });

  it('shows privacy consent warning before authorizing Gemini vision', async () => {
    vi.spyOn(api, 'fetchMonitors').mockResolvedValue(mockMonitors);
    const onPerceive = vi.fn().mockResolvedValue(undefined);

    render(
      <ScreenPerceptionModal
        isOpen={true}
        onClose={vi.fn()}
        onPerformPerception={onPerceive}
      />
    );

    await waitFor(() => {
      expect(screen.getByText(/MULTIMODAL VISION REASONING/i)).not.toBeNull();
    });

    // Click multimodal vision option
    fireEvent.click(screen.getByText(/MULTIMODAL VISION REASONING/i));

    // Shows explicit consent warning
    expect(screen.getByText(/EXTERNAL PROCESSING AUTHORIZATION/i)).not.toBeNull();
    expect(screen.getByText(/transmitted to the Google Gemini API for visual reasoning/i)).not.toBeNull();

    // Confirm consent
    const authorizeBtn = screen.getByText(/AUTHORIZE & INSPECT/i);
    fireEvent.click(authorizeBtn);

    expect(onPerceive).toHaveBeenCalledWith(
      'gemini_vision',
      1,
      true,
      expect.stringContaining('What is currently displayed')
    );
  });
});

