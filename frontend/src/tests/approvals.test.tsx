import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { ApprovalPreviewPanel } from '../components/ApprovalPreviewPanel';
import { ApprovalBubble } from '../components/ApprovalBubble';
import { ApprovalRequest } from '../types/contracts';
import * as api from '../services/api';

describe('ApprovalBubble Component', () => {
  const mockRequest: ApprovalRequest = {
    id: 'req-bubble-123',
    toolExecutionId: 'exec-bubble-456',
    actionSummary: 'Execute elevated operation: Close Visual Studio Code',
    toolName: 'windows_close_window',
    riskTier: 'CONSEQUENTIAL',
    parameters: { hwnd: 123456 },
    requestedAt: new Date().toISOString(),
    expiresAt: new Date(Date.now() + 300000).toISOString(),
    status: 'pending',
  };

  it('renders approval bubble with action summary, risk badge, and buttons', () => {
    render(
      <ApprovalBubble
        request={mockRequest}
        onApprove={vi.fn()}
        onDecline={vi.fn()}
      />
    );

    expect(screen.getByText(/CONSEQUENTIAL RISK/i)).not.toBeNull();
    expect(screen.getByText(/Execute elevated operation: Close Visual Studio Code/i)).not.toBeNull();
    expect(screen.getByText(/windows_close_window/i)).not.toBeNull();
    expect(screen.getByRole('button', { name: /APPROVE/i })).not.toBeNull();
    expect(screen.getByRole('button', { name: /DECLINE/i })).not.toBeNull();
  });

  it('calls onApprove callback with request id on button click', async () => {
    const onApprove = vi.fn().mockResolvedValue(undefined);
    render(
      <ApprovalBubble
        request={mockRequest}
        onApprove={onApprove}
        onDecline={vi.fn()}
      />
    );

    const approveBtn = screen.getByRole('button', { name: /APPROVE/i });
    fireEvent.click(approveBtn);

    expect(onApprove).toHaveBeenCalledWith('req-bubble-123');
    await waitFor(() => {
      expect(screen.getByText(/AUTHORIZATION GRANTED/i)).not.toBeNull();
    });
  });

  it('calls onDecline callback with request id on button click', async () => {
    const onDecline = vi.fn().mockResolvedValue(undefined);
    render(
      <ApprovalBubble
        request={mockRequest}
        onApprove={vi.fn()}
        onDecline={onDecline}
      />
    );

    const declineBtn = screen.getByRole('button', { name: /DECLINE/i });
    fireEvent.click(declineBtn);

    expect(onDecline).toHaveBeenCalledWith('req-bubble-123');
    await waitFor(() => {
      expect(screen.getByText(/AUTHORIZATION DECLINED/i)).not.toBeNull();
    });
  });

  it('renders resolved visual target details including coordinates, box, app name, and detection badge', () => {
    const visualClickRequest: ApprovalRequest = {
      id: 'req-click-999',
      toolExecutionId: 'exec-click-999',
      actionSummary: "Click on 'YouTube Video: How To Code' in Opera GX at screen coordinates (590, 415)",
      toolName: 'visual_click_element',
      riskTier: 'CONSEQUENTIAL',
      parameters: {
        x: 590,
        y: 415,
        target_description: 'YouTube Video: How To Code',
        app_name: 'Opera GX',
        window_title: 'YouTube - Opera GX',
        bounding_box: { left: 350, top: 280, width: 480, height: 270 },
        detection_method: 'visual_reasoning',
        confidence: 0.95,
      },
      requestedAt: new Date().toISOString(),
      expiresAt: new Date(Date.now() + 300000).toISOString(),
      status: 'pending',
    };

    render(
      <ApprovalBubble
        request={visualClickRequest}
        onApprove={vi.fn()}
        onDecline={vi.fn()}
      />
    );

    expect(screen.getAllByText(/Opera GX/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/YouTube Video: How To Code/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/\(590, 415\)/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/Visual AI 🧠/i)).not.toBeNull();
    expect(screen.getByText(/95% match/i)).not.toBeNull();
  });
});

describe('ApprovalPreviewPanel Component', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders initial empty state when no pending approvals exist', async () => {
    vi.spyOn(api, 'fetchPendingApprovals').mockResolvedValue([]);

    render(<ApprovalPreviewPanel />);

    expect(screen.getByText(/SECURITY GATEWAY/i)).not.toBeNull();
    expect(screen.getByText(/No authorization requests pending/i)).not.toBeNull();
  });

  it('renders simulated demo request when Simulate Demo button is clicked', async () => {
    vi.spyOn(api, 'fetchPendingApprovals').mockResolvedValue([]);
    const onRequestState = vi.fn();

    render(<ApprovalPreviewPanel onRequestApprovalState={onRequestState} />);

    const demoBtn = screen.getByRole('button', { name: /Simulate Demo/i });
    fireEvent.click(demoBtn);

    expect(screen.getByText(/CONSEQUENTIAL/i)).not.toBeNull();
    expect(screen.getByText(/Close desktop window/i)).not.toBeNull();
    expect(onRequestState).toHaveBeenCalled();
  });

  it('approves a request and triggers state cleanup callback', async () => {
    vi.spyOn(api, 'fetchPendingApprovals').mockResolvedValue([]);
    const onClearState = vi.fn();

    render(<ApprovalPreviewPanel onClearApprovalState={onClearState} />);

    // Trigger demo
    fireEvent.click(screen.getByRole('button', { name: /Simulate Demo/i }));

    const approveBtn = screen.getByRole('button', { name: /APPROVE/i });
    fireEvent.click(approveBtn);

    expect(screen.getByText(/APPROVED/i)).not.toBeNull();
    expect(onClearState).toHaveBeenCalled();
  });

  it('rejects a request and triggers state cleanup callback', async () => {
    vi.spyOn(api, 'fetchPendingApprovals').mockResolvedValue([]);
    const onClearState = vi.fn();

    render(<ApprovalPreviewPanel onClearApprovalState={onClearState} />);

    // Trigger demo
    fireEvent.click(screen.getByRole('button', { name: /Simulate Demo/i }));

    const rejectBtn = screen.getByRole('button', { name: /REJECT/i });
    fireEvent.click(rejectBtn);

    expect(screen.getByText(/REJECTED/i)).not.toBeNull();
    expect(onClearState).toHaveBeenCalled();
  });

  it('displays live backend approvals when fetched', async () => {
    vi.spyOn(api, 'fetchPendingApprovals').mockResolvedValue([
      {
        id: 'appr-live-999',
        toolExecutionId: 'exec-live-111',
        actionSummary: 'Launch authorized application: Notepad',
        toolName: 'windows_launch_app',
        riskTier: 'CONSEQUENTIAL',
        parameters: { app_id: 'notepad' },
        requestedAt: new Date().toISOString(),
        expiresAt: new Date(Date.now() + 300000).toISOString(),
        status: 'pending',
      },
    ]);

    render(<ApprovalPreviewPanel />);

    await waitFor(() => {
      expect(screen.getByText(/appr-live-999/i)).not.toBeNull();
      expect(screen.getByText(/Launch authorized application: Notepad/i)).not.toBeNull();
      expect(screen.getByText(/LIVE GATEWAY/i)).not.toBeNull();
    });
  });
});

