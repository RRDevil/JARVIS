import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { streamChatCompletion, ChatMessagePayload } from '../services/chatStream';
import { ArcReactor } from '../components/ArcReactor';
import { ScreenPerceptionModal } from '../components/ScreenPerceptionModal';
import { PerceptionProgress } from '../types/contracts';

describe('Screen Perception Lifecycle & State Synchronization', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('1 & 2: parses stage events in chatStream to update live perception progression', async () => {
    const sseChunks = [
      'event: message_start\ndata: {"model":"gemini-2.5-flash","request_id":"req-p1","session_id":"sess-p1","stage":"ANALYZING_VISION"}\n\n',
      'event: text_delta\ndata: {"request_id":"req-p1","delta":"Analysis: ","stage":"GENERATING"}\n\n',
      'event: text_delta\ndata: {"request_id":"req-p1","delta":"Clear screen."}\n\n',
      'event: message_complete\ndata: {"request_id":"req-p1","full_text":"Analysis: Clear screen.","stage":"COMPLETED"}\n\n',
    ];

    let chunkIndex = 0;
    const mockStream = new ReadableStream({
      pull(controller) {
        if (chunkIndex < sseChunks.length) {
          controller.enqueue(new TextEncoder().encode(sseChunks[chunkIndex]));
          chunkIndex++;
        } else {
          controller.close();
        }
      },
    });

    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      body: mockStream,
    }));

    const stages: string[] = [];
    const deltas: string[] = [];
    let completed = false;

    const messages: ChatMessagePayload[] = [{ role: 'user', content: 'What is on my screen?' }];

    await streamChatCompletion(messages, 'sess-p1', {
      onStageChange: (stage) => {
        stages.push(stage);
      },
      onDelta: (delta) => {
        deltas.push(delta);
      },
      onComplete: () => {
        completed = true;
      },
    });

    expect(stages).toEqual(['ANALYZING_VISION', 'GENERATING', 'COMPLETED']);
    expect(deltas).toEqual(['Analysis: ', 'Clear screen.']);
    expect(completed).toBe(true);
  });

  it('3 & 6: recovers safely when SSE stream terminates unexpectedly with text', async () => {
    // SSE stream closes without message_complete event
    const sseChunks = [
      'event: message_start\ndata: {"model":"gemini-2.5-flash","request_id":"req-p2","session_id":"sess-p2","stage":"ANALYZING_VISION"}\n\n',
      'event: text_delta\ndata: {"request_id":"req-p2","delta":"Partial analysis before disconnect."}\n\n',
    ];

    let chunkIndex = 0;
    const mockStream = new ReadableStream({
      pull(controller) {
        if (chunkIndex < sseChunks.length) {
          controller.enqueue(new TextEncoder().encode(sseChunks[chunkIndex]));
          chunkIndex++;
        } else {
          controller.close();
        }
      },
    });

    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      body: mockStream,
    }));

    let fullResult = '';
    let completed = false;

    await streamChatCompletion([{ role: 'user', content: 'Read screen' }], 'sess-p2', {
      onComplete: (fullText) => {
        completed = true;
        fullResult = fullText;
      },
    });

    // Fallback completion should fire with accumulated text so UI does not hang
    expect(completed).toBe(true);
    expect(fullResult).toBe('Partial analysis before disconnect.');
  });

  it('4 & 6: triggers onError when SSE stream closes with zero received text', async () => {
    // SSE stream closes without any text or complete event
    const sseChunks = [
      'event: message_start\ndata: {"model":"gemini-2.5-flash","request_id":"req-p3","session_id":"sess-p3"}\n\n',
    ];

    let chunkIndex = 0;
    const mockStream = new ReadableStream({
      pull(controller) {
        if (chunkIndex < sseChunks.length) {
          controller.enqueue(new TextEncoder().encode(sseChunks[chunkIndex]));
          chunkIndex++;
        } else {
          controller.close();
        }
      },
    });

    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      body: mockStream,
    }));

    let errorCode = '';
    let errorMessage = '';

    await streamChatCompletion([{ role: 'user', content: 'Read screen' }], 'sess-p3', {
      onError: (code, msg) => {
        errorCode = code;
        errorMessage = msg;
      },
    });

    expect(errorCode).toBe('STREAM_TERMINATED_PREMATURELY');
    expect(errorMessage).toContain('closed unexpectedly');
  });

  it('8: handles duplicate terminal events safely without crashing', async () => {
    const sseChunks = [
      'event: message_start\ndata: {"model":"gemini-2.5-flash","request_id":"req-p4"}\n\n',
      'event: text_delta\ndata: {"request_id":"req-p4","delta":"Final result."}\n\n',
      'event: message_complete\ndata: {"request_id":"req-p4","full_text":"Final result."}\n\n',
      'event: message_complete\ndata: {"request_id":"req-p4","full_text":"Final result."}\n\n', // duplicate
    ];

    let chunkIndex = 0;
    const mockStream = new ReadableStream({
      pull(controller) {
        if (chunkIndex < sseChunks.length) {
          controller.enqueue(new TextEncoder().encode(sseChunks[chunkIndex]));
          chunkIndex++;
        } else {
          controller.close();
        }
      },
    });

    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      body: mockStream,
    }));

    let completeCount = 0;

    await streamChatCompletion([{ role: 'user', content: 'Read screen' }], 'sess-p4', {
      onComplete: () => {
        completeCount++;
      },
    });

    // Handled safely without exception, terminal flag ensures single completion
    expect(completeCount).toBe(1);
  });

  it('5 & 7: ArcReactor displays specific perception stage badges when active', () => {
    const { rerender } = render(
      <ArcReactor assistantState="THINKING" perceptionStage="CAPTURING" latencyMs={null} />
    );
    expect(screen.getByText('CAPTURE')).not.toBeNull();

    rerender(
      <ArcReactor assistantState="THINKING" perceptionStage="READING_OCR" latencyMs={null} />
    );
    expect(screen.getByText('READ OCR')).not.toBeNull();

    rerender(
      <ArcReactor assistantState="THINKING" perceptionStage="ANALYZING_VISION" latencyMs={null} />
    );
    expect(screen.getByText('VISION AI')).not.toBeNull();

    rerender(
      <ArcReactor assistantState="RESPONDING" perceptionStage="GENERATING" latencyMs={null} />
    );
    expect(screen.getByText('SPEAKING')).not.toBeNull();

    rerender(
      <ArcReactor assistantState="IDLE" perceptionStage="COMPLETED" latencyMs={null} />
    );
    expect(screen.getByText('DONE')).not.toBeNull();

    rerender(
      <ArcReactor assistantState="IDLE" perceptionStage="CANCELLED" latencyMs={null} />
    );
    expect(screen.getByText('HALTED')).not.toBeNull();
  });

  it('5: ScreenPerceptionModal displays active stage stepper and allows operator cancellation', () => {
    const onCancel = vi.fn();
    const progress: PerceptionProgress = {
      requestId: 'percept-test-1',
      stage: 'ANALYZING_VISION',
      stageMessage: 'Transmitting frame to Gemini Vision neural model...',
      targetDescription: 'Active Window',
      mode: 'gemini_vision',
      startTime: Date.now() - 3000,
      elapsedMs: 3000,
      error: null,
    };

    render(
      <ScreenPerceptionModal
        isOpen={true}
        onClose={vi.fn()}
        onPerformPerception={vi.fn()}
        isProcessing={true}
        perceptionProgress={progress}
        onCancelPerception={onCancel}
      />
    );

    // Should render active stage badge and message
    expect(screen.getByText(/3\. VISION/i)).not.toBeNull();
    expect(screen.getByText(/Transmitting frame to Gemini Vision/i)).not.toBeNull();

    // Cancellation button should be present and clickable
    const cancelBtn = screen.getByText(/CANCEL OPERATION/i);
    expect(cancelBtn).not.toBeNull();
    fireEvent.click(cancelBtn);
    expect(onCancel).toHaveBeenCalled();
  });
});
