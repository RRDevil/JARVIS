import { useState, useEffect, useRef, useMemo, useCallback } from 'react';
import { ChatMessage } from '../types/contracts';

export type BubbleTaskStatus = 'Processing' | 'Recent result' | 'Completed';

export interface VisibleBubbleItem {
  message: ChatMessage;
  status: BubbleTaskStatus;
  isFading: boolean;
  turnIndex: number;
}

export interface UseBubbleConversationOptions {
  completedTimeoutMs?: number;   // Delay before 'Completed' tasks start fading (default 14s)
  recentResultTimeoutMs?: number; // Delay before 'Recent result' tasks fade (default 90s)
  fadeDurationMs?: number;        // Smooth exit animation duration (default 750ms)
}

interface ConversationTurn {
  turnIndex: number;
  userMessage?: ChatMessage;
  assistantMessages: ChatMessage[];
  allMessageIds: string[];
}

type TimerType = 'recent' | 'recent_expired' | 'completed' | 'completed_expired';

interface ScheduledTimer {
  timerId: any;
  type: TimerType;
}

/**
 * Custom hook to manage the lifecycle, status classification, and progressive
 * automated fading of text boxes in JARVIS compact bubble mode.
 *
 * Requirements:
 * 1. Texts up to Turn (N - 2) are cleared from the bubble overlay.
 * 2. Turn (N - 1) is marked as 'Completed' and fades after completedTimeoutMs (~14s).
 * 3. Turn N while active/streaming is marked as 'Processing'.
 * 4. Turn N when completed becomes 'Recent result' and stays for a much longer time (~90s)
 *    before fading, unless manually removed earlier.
 */
export function useBubbleConversation(
  messages: ChatMessage[],
  isStreaming: boolean,
  options?: UseBubbleConversationOptions
) {
  const completedTimeoutMs = options?.completedTimeoutMs ?? 14000;
  const recentResultTimeoutMs = options?.recentResultTimeoutMs ?? 90000;
  const fadeDurationMs = options?.fadeDurationMs ?? 750;

  // Track message IDs undergoing the 750ms slide-fade animation
  const [fadingIds, setFadingIds] = useState<Set<string>>(new Set());
  // Track individually dismissed message IDs
  const [dismissedIds, setDismissedIds] = useState<Set<string>>(new Set());
  // Track turns whose fade timer has completely expired
  const [expiredTurnIndices, setExpiredTurnIndices] = useState<Set<number>>(new Set());

  // Track active timers per turn index
  const turnTimersRef = useRef<Map<number, ScheduledTimer>>(new Map());

  // Group messages into distinct chronological turns
  const turns = useMemo<ConversationTurn[]>(() => {
    const result: ConversationTurn[] = [];
    let currentTurn: ConversationTurn | null = null;
    let turnCount = 0;

    for (const msg of messages) {
      if (msg.role === 'user') {
        turnCount++;
        currentTurn = {
          turnIndex: turnCount,
          userMessage: msg,
          assistantMessages: [],
          allMessageIds: [msg.id],
        };
        result.push(currentTurn);
      } else if (msg.role === 'assistant') {
        if (currentTurn) {
          currentTurn.assistantMessages.push(msg);
          currentTurn.allMessageIds.push(msg.id);
        } else {
          // Welcome or introductory message prior to any user command
          currentTurn = {
            turnIndex: 0,
            assistantMessages: [msg],
            allMessageIds: [msg.id],
          };
          result.push(currentTurn);
        }
      }
    }

    return result;
  }, [messages]);

  // Identify latest and previous turns
  const latestTurn = turns.length > 0 ? turns[turns.length - 1] : null;
  const latestTurnIndex = latestTurn ? latestTurn.turnIndex : 0;

  // Determine if a specific turn is actively generating or awaiting execution
  const isTurnProcessing = useCallback(
    (turn: ConversationTurn): boolean => {
      // 1. If this is the current turn and overall stream is active
      if (turn.turnIndex === latestTurnIndex && isStreaming) return true;
      // 2. If user message is marked pending
      if (turn.userMessage && (turn.userMessage.status as string) === 'pending') return true;
      // 3. If user message exists but no assistant message has arrived yet
      if (turn.userMessage && turn.assistantMessages.length === 0) return true;
      // 4. If any assistant message in this turn is currently streaming
      if (turn.assistantMessages.some((m) => m.status === 'streaming')) return true;
      return false;
    },
    [latestTurnIndex, isStreaming]
  );

  const isLatestProcessing = useMemo(() => {
    if (!latestTurn) return false;
    return isTurnProcessing(latestTurn);
  }, [latestTurn, isTurnProcessing]);

  // Manual dismissal of an individual bubble by user
  const dismissItem = useCallback(
    (messageId: string) => {
      setFadingIds((prev) => new Set(prev).add(messageId));
      setTimeout(() => {
        setDismissedIds((prev) => new Set(prev).add(messageId));
        setFadingIds((prev) => {
          const next = new Set(prev);
          next.delete(messageId);
          return next;
        });
      }, fadeDurationMs);
    },
    [fadeDurationMs]
  );

  // Clear all bubble items
  const clearAllBubbleItems = useCallback(() => {
    turnTimersRef.current.forEach(({ timerId }) => {
      if (timerId) clearTimeout(timerId);
    });
    turnTimersRef.current.clear();
    setDismissedIds(new Set(messages.map((m) => m.id)));
    setFadingIds(new Set());
  }, [messages]);

  // Timer scheduling effect (guaranteeing processing tasks never fade or disappear)
  useEffect(() => {
    const activeTimers = turnTimersRef.current;

    // If conversation was cleared/reset, only clear state if it actually holds stale entries
    if (messages.length === 1 && messages[0].id.startsWith('welcome-')) {
      activeTimers.forEach(({ timerId }) => {
        if (timerId) clearTimeout(timerId);
      });
      activeTimers.clear();
      if (dismissedIds.size > 0) setDismissedIds(new Set());
      if (fadingIds.size > 0) setFadingIds(new Set());
      if (expiredTurnIndices.size > 0) setExpiredTurnIndices(new Set());
      return;
    }

    if (!latestTurn || latestTurnIndex === 0) return;

    for (const turn of turns) {
      if (turn.turnIndex === 0) continue;
      const isProcessing = isTurnProcessing(turn);
      const existing = activeTimers.get(turn.turnIndex);

      if (isProcessing) {
        // Active processing: halt and remove any scheduled fade timer immediately
        if (existing?.timerId) {
          clearTimeout(existing.timerId);
          activeTimers.delete(turn.turnIndex);
        }
        // Protect turn from any existing fade-out/expiration
        if (expiredTurnIndices.has(turn.turnIndex)) {
          setExpiredTurnIndices((prev) => {
            const next = new Set(prev);
            next.delete(turn.turnIndex);
            return next;
          });
        }
        if (turn.allMessageIds.some((id) => fadingIds.has(id))) {
          setFadingIds((prev) => {
            const next = new Set(prev);
            turn.allMessageIds.forEach((id) => next.delete(id));
            return next;
          });
        }
      } else {
        // Not processing: schedule progressive fade depending on whether turn is current or completed
        if (turn.turnIndex === latestTurnIndex) {
          // Current turn completed -> transitions to 'Recent result' (~90s timeout)
          if (!existing || (existing.type !== 'recent' && existing.type !== 'recent_expired')) {
            if (existing?.timerId) {
              clearTimeout(existing.timerId);
            }

            const timerId = setTimeout(() => {
              activeTimers.set(turn.turnIndex, { timerId: null, type: 'recent_expired' });
              setFadingIds((prev) => {
                const next = new Set(prev);
                turn.allMessageIds.forEach((id) => next.add(id));
                return next;
              });

              setTimeout(() => {
                setExpiredTurnIndices((prev) => new Set(prev).add(turn.turnIndex));
                setFadingIds((prev) => {
                  const next = new Set(prev);
                  turn.allMessageIds.forEach((id) => next.delete(id));
                  return next;
                });
              }, fadeDurationMs);
            }, recentResultTimeoutMs);

            activeTimers.set(turn.turnIndex, { timerId, type: 'recent' });
          }
        } else {
          // Earlier turn completed -> transitions to 'Completed' (~14s timeout)
          if (!existing || (existing.type !== 'completed' && existing.type !== 'completed_expired')) {
            if (existing?.timerId) {
              clearTimeout(existing.timerId);
            }

            const timerId = setTimeout(() => {
              activeTimers.set(turn.turnIndex, { timerId: null, type: 'completed_expired' });
              setFadingIds((prev) => {
                const next = new Set(prev);
                turn.allMessageIds.forEach((id) => next.add(id));
                return next;
              });

              setTimeout(() => {
                setExpiredTurnIndices((prev) => new Set(prev).add(turn.turnIndex));
                setFadingIds((prev) => {
                  const next = new Set(prev);
                  turn.allMessageIds.forEach((id) => next.delete(id));
                  return next;
                });
              }, fadeDurationMs);
            }, completedTimeoutMs);

            activeTimers.set(turn.turnIndex, { timerId, type: 'completed' });
          }
        }
      }
    }
  }, [
    turns,
    latestTurn,
    latestTurnIndex,
    isTurnProcessing,
    completedTimeoutMs,
    recentResultTimeoutMs,
    fadeDurationMs,
    messages,
    dismissedIds.size,
    fadingIds,
    expiredTurnIndices,
  ]);

  // Clean up all timers on unmount
  useEffect(() => {
    const activeTimers = turnTimersRef.current;
    return () => {
      activeTimers.forEach(({ timerId }) => {
        if (timerId) clearTimeout(timerId);
      });
      activeTimers.clear();
    };
  }, []);

  // Compute visible items to render
  const visibleItems = useMemo<VisibleBubbleItem[]>(() => {
    if (!latestTurn) return [];

    const items: VisibleBubbleItem[] = [];
    const minTurnIndex = latestTurnIndex >= 1 ? latestTurnIndex - 1 : 0;

    for (const turn of turns) {
      const turnProcessing = isTurnProcessing(turn);

      // Processing items must NEVER be pruned by index, initial welcome rules, or expired indices
      if (!turnProcessing) {
        // 1. Prune all turns older than (latestTurnIndex - 1)
        if (latestTurnIndex >= 1 && turn.turnIndex < minTurnIndex) {
          continue;
        }
        // 2. Prune initial welcome message once real conversation starts
        if (latestTurnIndex >= 1 && turn.turnIndex === 0) {
          continue;
        }
        // 3. Prune turns that have expired after fading
        if (expiredTurnIndices.has(turn.turnIndex)) {
          continue;
        }
      }

      const isCurrent = turn.turnIndex === latestTurnIndex;

      // User command message
      if (turn.userMessage && !dismissedIds.has(turn.userMessage.id)) {
        const userStatus: BubbleTaskStatus = turnProcessing ? 'Processing' : 'Completed';

        items.push({
          message: turn.userMessage,
          status: userStatus,
          isFading: turnProcessing ? false : fadingIds.has(turn.userMessage.id),
          turnIndex: turn.turnIndex,
        });
      }

      // Assistant response messages
      for (const asstMsg of turn.assistantMessages) {
        if (!dismissedIds.has(asstMsg.id)) {
          let asstStatus: BubbleTaskStatus = 'Completed';
          if (turnProcessing || asstMsg.status === 'streaming') {
            asstStatus = 'Processing';
          } else if (isCurrent) {
            asstStatus = 'Recent result';
          } else {
            asstStatus = 'Completed';
          }

          items.push({
            message: asstMsg,
            status: asstStatus,
            isFading: turnProcessing ? false : fadingIds.has(asstMsg.id),
            turnIndex: turn.turnIndex,
          });
        }
      }
    }

    return items;
  }, [
    turns,
    latestTurn,
    latestTurnIndex,
    isTurnProcessing,
    dismissedIds,
    fadingIds,
    expiredTurnIndices,
  ]);

  return {
    visibleItems,
    dismissItem,
    clearAllBubbleItems,
    isLatestProcessing,
    latestTurnIndex,
  };
}
