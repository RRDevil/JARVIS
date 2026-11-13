import { describe, it, expect, vi, beforeEach } from 'vitest';
import { streamChatCompletion, ChatMessagePayload } from '../services/chatStream';

describe('ChatStream SSE Client Service', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('parses SSE blocks and dispatches callbacks correctly', async () => {
    const sseChunks = [
      'event: message_start\ndata: {"model":"gemini-2.5-flash","request_id":"req-1","session_id":"sess-1"}\n\n',
      'event: text_delta\ndata: {"request_id":"req-1","delta":"System "}\n\n',
      'event: text_delta\ndata: {"request_id":"req-1","delta":"online."}\n\n',
      'event: usage\ndata: {"request_id":"req-1","usage":{"input_tokens":5,"output_tokens":2,"total_tokens":7}}\n\n',
      'event: message_complete\ndata: {"request_id":"req-1","full_text":"System online.","duration_ms":120}\n\n',
    ];

    // Mock readable stream
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

    const deltas: string[] = [];
    let completedText = '';
    let reportedModel = '';
    let totalTokens = 0;

    const messages: ChatMessagePayload[] = [{ role: 'user', content: 'Status check' }];

    await streamChatCompletion(messages, 'sess-1', {
      onStart: (model) => {
        reportedModel = model;
      },
      onDelta: (delta) => {
        deltas.push(delta);
      },
      onUsage: (usage) => {
        totalTokens = usage.total_tokens || 0;
      },
      onComplete: (fullText) => {
        completedText = fullText;
      },
    });

    expect(reportedModel).toBe('gemini-2.5-flash');
    expect(deltas).toEqual(['System ', 'online.']);
    expect(totalTokens).toBe(7);
    expect(completedText).toBe('System online.');
  });

  it('invokes onError when server returns non-200 HTTP status', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false,
      status: 422,
      statusText: 'Unprocessable Entity',
      json: async () => ({ detail: 'Exceeded maximum turn limit' }),
    }));

    let errorCode = '';
    let errorMessage = '';

    await streamChatCompletion(
      [{ role: 'user', content: 'Hi' }],
      'sess-test',
      {
        onError: (code, msg) => {
          errorCode = code;
          errorMessage = msg;
        },
      }
    );

    expect(errorCode).toBe('HTTP_ERROR');
    expect(errorMessage).toContain('Exceeded maximum turn limit');
  });

  it('handles client cancellation via AbortController', async () => {
    const controller = new AbortController();

    // Mock fetch that throws AbortError
    vi.stubGlobal('fetch', vi.fn().mockImplementation(() => {
      const err = new Error('The user aborted a request.');
      err.name = 'AbortError';
      return Promise.reject(err);
    }));

    let errorCode = '';
    controller.abort();

    await streamChatCompletion(
      [{ role: 'user', content: 'Cancel me' }],
      'sess-test',
      {
        onError: (code) => {
          errorCode = code;
        },
      },
      controller.signal
    );

    expect(errorCode).toBe('CLIENT_CANCELLED');
  });

  it('correctly processes multi-step tool execution events and preserves AWAITING_APPROVAL stage', async () => {
    const sseChunks = [
      'event: message_start\ndata: {"model":"gemini-3.5-flash-lite","request_id":"req-multi","session_id":"sess-m"}\n\n',
      'event: tool_start\ndata: {"request_id":"req-multi","tool_name":"windows_launch_app","stage":"EXECUTING"}\n\n',
      'event: tool_result\ndata: {"request_id":"req-multi","tool_name":"windows_launch_app","stage":"VERIFYING","tool_status":"success"}\n\n',
      'event: tool_start\ndata: {"request_id":"req-multi","tool_name":"visual_click_element","stage":"EXECUTING"}\n\n',
      'event: tool_result\ndata: {"request_id":"req-multi","tool_name":"visual_click_element","stage":"AWAITING_APPROVAL","tool_status":"requires_approval"}\n\n',
      'event: text_delta\ndata: {"request_id":"req-multi","delta":"I need your authorization to click the Submit button."}\n\n',
      'event: message_complete\ndata: {"request_id":"req-multi","full_text":"I need your authorization to click the Submit button.","stage":"AWAITING_APPROVAL"}\n\n',
    ];

    let chunkIdx = 0;
    const mockStream = new ReadableStream({
      pull(controller) {
        if (chunkIdx < sseChunks.length) {
          controller.enqueue(new TextEncoder().encode(sseChunks[chunkIdx++]));
        } else {
          controller.close();
        }
      },
    });

    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      body: mockStream,
    }));

    const toolEvents: Array<{ tool: string; stage: string; status?: string }> = [];
    const stages: string[] = [];
    let completionCalls = 0;
    let finalStage = '';

    await streamChatCompletion(
      [{ role: 'user', content: 'Launch app and click submit' }],
      'sess-m',
      {
        onStageChange: (stage) => stages.push(stage),
        onToolCall: (toolName, stage, toolStatus) => toolEvents.push({ tool: toolName, stage, status: toolStatus }),
        onComplete: (_text, _duration, stage) => {
          completionCalls++;
          finalStage = stage || '';
        },
      }
    );

    // Verify all tool start and result events were captured
    expect(toolEvents).toHaveLength(4);
    expect(toolEvents[0]).toEqual({ tool: 'windows_launch_app', stage: 'EXECUTING', status: undefined });
    expect(toolEvents[1]).toEqual({ tool: 'windows_launch_app', stage: 'VERIFYING', status: 'success' });
    expect(toolEvents[2]).toEqual({ tool: 'visual_click_element', stage: 'EXECUTING', status: undefined });
    expect(toolEvents[3]).toEqual({ tool: 'visual_click_element', stage: 'AWAITING_APPROVAL', status: 'requires_approval' });

    // Verify stage transitions
    expect(stages).toContain('EXECUTING');
    expect(stages).toContain('VERIFYING');
    expect(stages).toContain('AWAITING_APPROVAL');

    // Verify exactly ONE terminal event fired
    expect(completionCalls).toBe(1);
    expect(finalStage).toBe('AWAITING_APPROVAL');
  });
});

