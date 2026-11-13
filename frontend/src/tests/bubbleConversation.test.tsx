import { describe, it, expect, vi } from 'vitest';
import { renderHook, act, render, screen, fireEvent, waitFor } from '@testing-library/react';
import { useBubbleConversation } from '../hooks/useBubbleConversation';
import { QuickCommandBar } from '../components/QuickCommandBar';
import { ChatMessage } from '../types/contracts';

describe('useBubbleConversation Hook', () => {
  const createMsg = (
    id: string,
    role: 'user' | 'assistant',
    content: string,
    status: 'streaming' | 'completed' | 'error' = 'completed'
  ): ChatMessage => ({
    id,
    role,
    content,
    timestamp: '12:00:00',
    status,
  });

  it('marks initial welcome message as Recent result', () => {
    const welcome = createMsg('welcome-0', 'assistant', 'Good day, Sir.');
    const { result } = renderHook(() => useBubbleConversation([welcome], false));

    expect(result.current.visibleItems).toHaveLength(1);
    expect(result.current.visibleItems[0].status).toBe('Recent result');
    expect(result.current.visibleItems[0].message.id).toBe('welcome-0');
  });

  it('marks active command and streaming assistant response as Processing', () => {
    const cmd1 = createMsg('u-1', 'user', 'What is on my screen?');
    const asst1 = createMsg('a-1', 'assistant', '', 'streaming');

    const { result } = renderHook(() =>
      useBubbleConversation([cmd1, asst1], true)
    );

    expect(result.current.visibleItems).toHaveLength(2);
    expect(result.current.visibleItems[0].status).toBe('Processing'); // user command
    expect(result.current.visibleItems[1].status).toBe('Processing'); // assistant response
    expect(result.current.isLatestProcessing).toBe(true);
  });

  it('transitions assistant to Recent result when generation completes', () => {
    const cmd1 = createMsg('u-1', 'user', 'What is on my screen?');
    const asst1 = createMsg('a-1', 'assistant', 'You have Notepad open.', 'completed');

    const { result } = renderHook(() =>
      useBubbleConversation([cmd1, asst1], false)
    );

    expect(result.current.visibleItems).toHaveLength(2);
    expect(result.current.visibleItems[0].status).toBe('Completed'); // user command finished
    expect(result.current.visibleItems[1].status).toBe('Recent result'); // fresh assistant result
    expect(result.current.isLatestProcessing).toBe(false);
  });

  it('transitions previous turn to Completed when a new command is given', () => {
    const turn1_user = createMsg('u-1', 'user', 'Command 1');
    const turn1_asst = createMsg('a-1', 'assistant', 'Result 1', 'completed');
    const turn2_user = createMsg('u-2', 'user', 'Command 2');
    const turn2_asst = createMsg('a-2', 'assistant', '', 'streaming');

    const { result } = renderHook(() =>
      useBubbleConversation([turn1_user, turn1_asst, turn2_user, turn2_asst], true)
    );

    expect(result.current.visibleItems).toHaveLength(4);
    // Turn 1 (previous) is marked Completed
    expect(result.current.visibleItems[0].status).toBe('Completed');
    expect(result.current.visibleItems[1].status).toBe('Completed');
    // Turn 2 (current) is marked Processing
    expect(result.current.visibleItems[2].status).toBe('Processing');
    expect(result.current.visibleItems[3].status).toBe('Processing');
  });

  it('prunes all turns prior to Turn (N - 1) (User Scenario: command 1..5)', () => {
    // Commands 1 to 5 with results 1 to 4 completed, command 5 currently processing
    const messages: ChatMessage[] = [
      createMsg('u-1', 'user', 'Command 1'),
      createMsg('a-1', 'assistant', 'Result 1', 'completed'),
      createMsg('u-2', 'user', 'Command 2'),
      createMsg('a-2', 'assistant', 'Result 2', 'completed'),
      createMsg('u-3', 'user', 'Command 3'),
      createMsg('a-3', 'assistant', 'Result 3', 'completed'),
      createMsg('u-4', 'user', 'Command 4'),
      createMsg('a-4', 'assistant', 'Result 4', 'completed'),
      createMsg('u-5', 'user', 'Command 5'),
      createMsg('a-5', 'assistant', '', 'streaming'),
    ];

    const { result } = renderHook(() => useBubbleConversation(messages, true));

    // Results 1 to 3 should be cleared! Only Turn 4 and Turn 5 remain.
    const visibleIds = result.current.visibleItems.map((item) => item.message.id);
    expect(visibleIds).toEqual(['u-4', 'a-4', 'u-5', 'a-5']);

    // Turn 4 items are marked as Completed
    const turn4_user = result.current.visibleItems.find((i) => i.message.id === 'u-4');
    const turn4_asst = result.current.visibleItems.find((i) => i.message.id === 'a-4');
    expect(turn4_user?.status).toBe('Completed');
    expect(turn4_asst?.status).toBe('Completed');

    // Turn 5 items are marked as Processing
    const turn5_user = result.current.visibleItems.find((i) => i.message.id === 'u-5');
    const turn5_asst = result.current.visibleItems.find((i) => i.message.id === 'a-5');
    expect(turn5_user?.status).toBe('Processing');
    expect(turn5_asst?.status).toBe('Processing');
  });

  it('fades out Completed turn after completedTimeoutMs', async () => {
    const turn1_user = createMsg('u-1', 'user', 'Command 1');
    const turn1_asst = createMsg('a-1', 'assistant', 'Result 1', 'completed');
    const turn2_user = createMsg('u-2', 'user', 'Command 2');
    const turn2_asst = createMsg('a-2', 'assistant', 'Result 2', 'completed');

    const { result } = renderHook(() =>
      useBubbleConversation([turn1_user, turn1_asst, turn2_user, turn2_asst], false, {
        completedTimeoutMs: 60,
        recentResultTimeoutMs: 5000,
        fadeDurationMs: 40,
      })
    );

    // Initially Turn 1 and Turn 2 are visible
    expect(result.current.visibleItems).toHaveLength(4);

    // Wait past completed timeout + fade duration (60ms + 40ms = 100ms)
    await waitFor(
      () => {
        const remainingIds = result.current.visibleItems.map((i) => i.message.id);
        expect(remainingIds).toEqual(['u-2', 'a-2']);
      },
      { timeout: 1500 }
    );

    // Turn 2 remains as Recent result
    expect(result.current.visibleItems[1].status).toBe('Recent result');
  });

  it('supports manual dismissal of individual bubbles', async () => {
    const cmd1 = createMsg('u-1', 'user', 'Command 1');
    const asst1 = createMsg('a-1', 'assistant', 'Result 1', 'completed');

    const { result } = renderHook(() =>
      useBubbleConversation([cmd1, asst1], false, {
        fadeDurationMs: 30,
      })
    );

    expect(result.current.visibleItems).toHaveLength(2);

    // User clicks manual dismiss on cmd1
    act(() => {
      result.current.dismissItem('u-1');
    });

    // Wait past fade duration (30ms)
    await waitFor(
      () => {
        expect(result.current.visibleItems.map((i) => i.message.id)).toEqual(['a-1']);
      },
      { timeout: 500 }
    );
  });

  it('guarantees turns actively being processed never disappear or fade out while processing', async () => {
    // Turn 1 is still streaming/processing
    const turn1_user = createMsg('u-1', 'user', 'Open notepad and calculate');
    const turn1_asst = createMsg('a-1', 'assistant', 'Working on it...', 'streaming');
    // Turn 2 is submitted
    const turn2_user = createMsg('u-2', 'user', 'Next command');
    const turn2_asst = createMsg('a-2', 'assistant', 'Second response...', 'streaming');

    const { result } = renderHook(() =>
      useBubbleConversation([turn1_user, turn1_asst, turn2_user, turn2_asst], true, {
        completedTimeoutMs: 50,
        fadeDurationMs: 30,
      })
    );

    // Both turns must remain visible because they are still processing
    expect(result.current.visibleItems).toHaveLength(4);
    expect(result.current.visibleItems.find((i) => i.message.id === 'u-1')?.status).toBe('Processing');
    expect(result.current.visibleItems.find((i) => i.message.id === 'a-1')?.status).toBe('Processing');
    expect(result.current.visibleItems.find((i) => i.message.id === 'u-2')?.status).toBe('Processing');
    expect(result.current.visibleItems.find((i) => i.message.id === 'a-2')?.status).toBe('Processing');

    // Wait past the normal completed timeout (50ms + 30ms = 80ms)
    await new Promise((r) => setTimeout(r, 120));

    // Must STILL be visible and not faded
    expect(result.current.visibleItems).toHaveLength(4);
    expect(result.current.visibleItems.every((i) => i.isFading === false)).toBe(true);
  });
});

describe('QuickCommandBar UI Integration with Task Statuses', () => {
  it('renders status badges and allows manual dismissal', () => {
    const messages: ChatMessage[] = [
      {
        id: 'u-10',
        role: 'user',
        content: 'Check monitor status',
        timestamp: '12:00',
        status: 'completed',
      },
      {
        id: 'a-10',
        role: 'assistant',
        content: 'Primary monitor is 1920x1080.',
        timestamp: '12:00',
        status: 'completed',
      },
    ];

    render(
      <QuickCommandBar
        onOpenDashboard={vi.fn()}
        onClose={vi.fn()}
        messages={messages}
        isStreaming={false}
      />
    );

    // Status badges should be rendered in the DOM
    expect(screen.getByText('RECENT RESULT')).not.toBeNull();
    expect(screen.getByText('COMPLETED')).not.toBeNull();

    // Dismiss button should be present
    const dismissBtns = screen.getAllByTitle(/Dismiss/i);
    expect(dismissBtns.length).toBeGreaterThan(0);

    // Clicking dismiss on first button triggers dismissal
    fireEvent.click(dismissBtns[0]);
  });
});
