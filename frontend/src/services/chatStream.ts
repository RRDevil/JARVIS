/**
 * JARVIS SSE Streaming Chat Client.
 *
 * Communicates with POST /api/v1/chat/stream, manages AbortController cancellation,
 * parses Server-Sent Events, and reports metrics.
 */

import { TaskLifecycleEvent } from '../types/narration';

export interface ChatMessagePayload {
  role: 'user' | 'assistant' | 'system';
  content: string;
  image_data?: string;
  image_mime_type?: string;
}

export interface StreamUsageMetadata {
  input_tokens?: number;
  output_tokens?: number;
  total_tokens?: number;
}

export interface StreamMetrics {
  model?: string;
  timeToFirstTokenMs?: number;
  totalDurationMs?: number;
  usage?: StreamUsageMetadata;
}

export interface StreamCallbacks {
  onStart?: (model: string, requestId: string, sessionId: string) => void;
  onDelta?: (delta: string) => void;
  onUsage?: (usage: StreamUsageMetadata) => void;
  onComplete?: (fullText: string, durationMs?: number, stage?: string) => void;
  onError?: (errorCode: string, errorMessage: string) => void;
  onStageChange?: (stage: string, requestId?: string) => void;
  onToolCall?: (toolName: string, stage: string, toolStatus?: string) => void;
  onNarration?: (event: TaskLifecycleEvent) => void;
}

export async function streamChatCompletion(
  messages: ChatMessagePayload[],
  sessionId: string,
  callbacks: StreamCallbacks,
  signal?: AbortSignal
): Promise<void> {
  const BACKEND_URL = 'http://127.0.0.1:8000';
  const endpoint = window.location.port === '5173' ? '/api/v1/chat/stream' : `${BACKEND_URL}/api/v1/chat/stream`;

  const startTime = performance.now();
  let firstTokenReceived = false;
  let terminalEventReceived = false;
  let accumulatedText = '';

  let response: Response;
  try {
    response = await fetch(endpoint, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'text/event-stream',
      },
      body: JSON.stringify({
        messages,
        session_id: sessionId,
      }),
      signal,
    });
  } catch (err: any) {
    if (err.name === 'AbortError') {
      callbacks.onError?.('CLIENT_CANCELLED', 'Generation stopped by user.');
    } else {
      callbacks.onError?.('NETWORK_ERROR', err.message || 'Failed to reach JARVIS backend.');
    }
    return;
  }

  if (!response.ok) {
    let errorDetail = `HTTP ${response.status}: ${response.statusText}`;
    try {
      const errJson = await response.json();
      if (errJson && errJson.detail) {
        errorDetail = typeof errJson.detail === 'string' ? errJson.detail : JSON.stringify(errJson.detail);
      }
    } catch {
      // Keep default errorDetail
    }
    callbacks.onError?.('HTTP_ERROR', errorDetail);
    return;
  }

  if (!response.body) {
    callbacks.onError?.('NO_BODY', 'Response stream contains no readable body.');
    return;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder('utf-8');
  let buffer = '';

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const blocks = buffer.split('\n\n');
      // Keep unfinished block in buffer
      buffer = blocks.pop() || '';

      for (const block of blocks) {
        if (!block.trim()) continue;
        const lines = block.split('\n');
        let eventType = 'message';
        let dataJson = '';

        for (const line of lines) {
          if (line.startsWith('event:')) {
            eventType = line.replace('event:', '').trim();
          } else if (line.startsWith('data:')) {
            dataJson = line.replace('data:', '').trim();
          }
        }

        if (!dataJson) continue;

        try {
          const data = JSON.parse(dataJson);

          // Propagate real-time processing stage if provided by backend
          if (data.stage) {
            callbacks.onStageChange?.(data.stage, data.request_id);
          }

          switch (eventType) {
            case 'message_start':
              callbacks.onStart?.(data.model, data.request_id, data.session_id);
              break;

            case 'text_delta':
              if (!firstTokenReceived) {
                firstTokenReceived = true;
                const ttft = Math.round(performance.now() - startTime);
                // Report TTFT internally or through custom handling
                (window as any).__jarvis_last_ttft = ttft;
              }
              if (data.delta) {
                accumulatedText += data.delta;
                callbacks.onDelta?.(data.delta);
              }
              break;

            case 'usage':
              if (data.usage) {
                callbacks.onUsage?.(data.usage);
              }
              break;

            case 'tool_start':
            case 'tool_result':
              callbacks.onToolCall?.(
                data.tool_name,
                data.stage || (eventType === 'tool_start' ? 'EXECUTING' : 'VERIFYING'),
                data.tool_status
              );
              break;

            case 'narration':
              if (data.narration || data.event_type) {
                callbacks.onNarration?.(data.narration || data);
              }
              break;

            case 'message_complete':
              if (!terminalEventReceived) {
                terminalEventReceived = true;
                callbacks.onComplete?.(data.full_text || accumulatedText, data.duration_ms, data.stage);
              }
              break;

            case 'error':
              if (!terminalEventReceived) {
                terminalEventReceived = true;
                callbacks.onError?.(data.error_code || 'UNKNOWN_ERROR', data.error_message || 'Stream error');
              }
              break;
          }
        } catch (e) {
          console.warn('Failed to parse SSE JSON chunk:', dataJson, e);
        }
      }
    }

    // Terminal state guarantee: if connection completed without an explicit terminal event
    if (!terminalEventReceived) {
      if (accumulatedText.length > 0) {
        callbacks.onComplete?.(accumulatedText, Math.round(performance.now() - startTime));
      } else {
        callbacks.onError?.('STREAM_TERMINATED_PREMATURELY', 'Server connection closed unexpectedly before response was synthesized.');
      }
    }
  } catch (err: any) {
    if (err.name === 'AbortError') {
      callbacks.onError?.('CLIENT_CANCELLED', 'Generation stopped by user.');
    } else {
      callbacks.onError?.('STREAM_READ_ERROR', err.message || 'Stream reading disrupted.');
    }
  } finally {
    reader.releaseLock();
  }
}

