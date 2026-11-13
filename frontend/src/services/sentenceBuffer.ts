import { normalizeTextForSpeech } from './textNormalizer';
import { speechTiming, BoundaryType } from './speechTiming';

export interface SentenceBufferOptions {
  minSentenceLength?: number;
  maxBufferLength?: number;
  flushTimeoutMs?: number;
  onSentence: (sentence: string, index: number, isLast: boolean, boundaryType: BoundaryType) => void;
}

const COMMON_ABBREVIATIONS = new Set([
  'mr',
  'mrs',
  'ms',
  'dr',
  'prof',
  'sr',
  'jr',
  'vs',
  'etc',
  'fig',
  'al',
  'inc',
  'ltd',
  'corp',
  'e.g',
  'i.e',
]);

/**
 * Intelligent Sentence Buffer.
 * Splits incoming streamed text into natural sentence-sized units for TTS synthesis.
 * Protects abbreviations, decimals, and clauses, and detects boundary pause types.
 */
export class SentenceBuffer {
  private buffer = '';
  private rawAccumulated = '';
  private sentenceIndex = 0;
  private minSentenceLength: number;
  private maxBufferLength: number;
  private flushTimeoutMs: number;
  private onSentence: (sentence: string, index: number, isLast: boolean, boundaryType: BoundaryType) => void;
  private timeoutId: any = null;
  private isCompleted = false;

  constructor(options: SentenceBufferOptions) {
    this.minSentenceLength = options.minSentenceLength ?? 25;
    this.maxBufferLength = options.maxBufferLength ?? 180;
    this.flushTimeoutMs = options.flushTimeoutMs ?? 900;
    this.onSentence = options.onSentence;
  }

  /**
   * Append a new token delta from Gemini SSE stream.
   */
  public append(chunk: string): void {
    if (this.isCompleted || !chunk) return;

    this.rawAccumulated += chunk;
    this.buffer += chunk;

    // Reset inactivity flush timer
    this.resetTimer();

    this.processBuffer(false);
  }

  /**
   * Evaluates the current buffer and extracts completed sentences.
   */
  private processBuffer(forceFlush: boolean): void {
    while (this.buffer.length > 0) {
      const splitIndex = this.findSentenceBoundary(this.buffer, forceFlush);
      if (splitIndex === -1) {
        break;
      }

      const rawSegment = this.buffer.slice(0, splitIndex).trim();
      this.buffer = this.buffer.slice(splitIndex).trimStart();

      const boundaryType = speechTiming.detectBoundaryType(rawSegment);
      const normalized = normalizeTextForSpeech(rawSegment);
      if (normalized.length > 0) {
        const idx = this.sentenceIndex++;
        this.onSentence(normalized, idx, false, boundaryType);
      }
    }
  }

  /**
   * Scans text to find a natural sentence boundary.
   */
  private findSentenceBoundary(text: string, force: boolean): number {
    if (!text) return -1;

    // 1. Paragraph breaks take top priority as major structural boundaries
    const paraIdx = text.indexOf('\n\n');
    if (paraIdx !== -1 && (paraIdx >= this.minSentenceLength || force)) {
      return paraIdx + 2;
    }

    // 2. Regex matching sentence terminating punctuation (. ! ?) followed by space or end
    const punctRegex = /([.!?]+)(\s+|$)/g;
    let match: RegExpExecArray | null;

    while ((match = punctRegex.exec(text)) !== null) {
      const punctEnd = match.index + match[1].length;
      const precedingText = text.slice(0, match.index).trim();

      // Check if this punctuation is part of a decimal number (e.g. 3.14)
      if (match[1] === '.' && match.index > 0 && match.index + 1 < text.length) {
        const prevChar = text[match.index - 1];
        const nextChar = text[match.index + 1];
        if (/\d/.test(prevChar) && /\d/.test(nextChar)) {
          continue; // Skip decimal
        }
      }

      // Check for common abbreviations (Dr., Mr., e.g., etc.)
      const lastWordMatch = precedingText.match(/(?:^|\s)([a-zA-Z]{1,5})$/);
      if (lastWordMatch && match[1] === '.') {
        const lastWord = lastWordMatch[1].toLowerCase();
        if (COMMON_ABBREVIATIONS.has(lastWord)) {
          continue; // Skip abbreviation
        }
      }

      // Length check: ensure candidate segment meets minSentenceLength and does not exceed maxBufferLength
      if (punctEnd >= this.minSentenceLength || force) {
        if (punctEnd <= this.maxBufferLength) {
          return match.index + match[0].length;
        }
        // Punctuation is beyond maxBufferLength; break and allow earlier clause split
        break;
      }
    }

    // 3. If buffer exceeds maxBufferLength, try splitting at a secondary boundary (comma, semicolon, colon, dash)
    if (text.length >= this.maxBufferLength || force) {
      const secondaryRegex = /([,;:—–-]+)(\s+)/g;
      let lastSecondarySplit = -1;
      while ((match = secondaryRegex.exec(text)) !== null) {
        const pos = match.index + match[0].length;
        if (pos >= this.minSentenceLength) {
          lastSecondarySplit = pos;
          break;
        }
      }

      if (lastSecondarySplit !== -1) {
        return lastSecondarySplit;
      }

      // Fallback: split at last space before maxBufferLength
      const spaceIndex = text.lastIndexOf(' ', this.maxBufferLength);
      if (spaceIndex >= this.minSentenceLength) {
        return spaceIndex + 1;
      }

      // If forced and still no split, return full length
      if (force && text.length > 0) {
        return text.length;
      }
    }

    return -1;
  }

  private resetTimer(): void {
    this.clearTimer();
    this.timeoutId = setTimeout(() => {
      // Idle timeout elapsed without punctuation: process buffer with force if long enough
      if (this.buffer.trim().length >= this.minSentenceLength) {
        this.processBuffer(true);
      }
    }, this.flushTimeoutMs);
  }

  private clearTimer(): void {
    if (this.timeoutId) {
      clearTimeout(this.timeoutId);
      this.timeoutId = null;
    }
  }

  /**
   * Flushes any remaining un-synthesized text when stream completes or ends.
   */
  public flush(isLast = true): void {
    this.clearTimer();
    this.isCompleted = isLast;

    if (this.buffer.trim().length > 0) {
      const rawSegment = this.buffer.trim();
      this.buffer = '';
      const boundaryType = speechTiming.detectBoundaryType(rawSegment);
      const normalized = normalizeTextForSpeech(rawSegment);
      if (normalized.length > 0) {
        const idx = this.sentenceIndex++;
        this.onSentence(normalized, idx, isLast, boundaryType);
        return;
      }
    }

    if (isLast) {
      // The last actual emitted sentence was (this.sentenceIndex - 1)
      const lastEmittedIdx = Math.max(-1, this.sentenceIndex - 1);
      this.onSentence('', lastEmittedIdx, true, 'neutral');
    }
  }

  /**
   * Resets and clears all internal buffers and timers.
   */
  public reset(): void {
    this.clearTimer();
    this.buffer = '';
    this.rawAccumulated = '';
    this.sentenceIndex = 0;
    this.isCompleted = false;
  }
}
