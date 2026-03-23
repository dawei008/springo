import { describe, it, expect } from 'vitest';
import { extractTextContent, isToolResultOnlyMessage } from './messageHelpers';
import type { Message } from '@/types';

describe('extractTextContent', () => {
  it('returns empty string for undefined', () => {
    expect(extractTextContent(undefined)).toBe('');
  });

  it('returns the string directly for string content', () => {
    expect(extractTextContent('hello world')).toBe('hello world');
  });

  it('returns empty string for empty array', () => {
    expect(extractTextContent([])).toBe('');
  });

  it('extracts text from text blocks', () => {
    const content = [
      { type: 'text' as const, text: 'Hello' },
      { type: 'text' as const, text: 'World' },
    ];
    expect(extractTextContent(content)).toBe('Hello\nWorld');
  });

  it('returns [Image] for image blocks', () => {
    const content = [
      { type: 'image' as const, source: { type: 'base64' as const, media_type: 'image/png' as const, data: '' } },
    ];
    expect(extractTextContent(content)).toBe('[Image]');
  });

  it('skips tool_use and tool_result blocks', () => {
    const content = [
      { type: 'text' as const, text: 'result' },
      { type: 'tool_use' as const, id: '1', name: 'test', input: {} },
      { type: 'tool_result' as const, tool_use_id: '1', content: 'ok' },
    ];
    expect(extractTextContent(content)).toBe('result');
  });

  it('handles mixed content with text and images', () => {
    const content = [
      { type: 'text' as const, text: 'Look at this:' },
      { type: 'image' as const, source: { type: 'base64' as const, media_type: 'image/png' as const, data: '' } },
    ];
    expect(extractTextContent(content)).toBe('Look at this:\n[Image]');
  });

  it('handles text block with empty text', () => {
    const content = [{ type: 'text' as const, text: '' }];
    expect(extractTextContent(content)).toBe('');
  });
});

describe('isToolResultOnlyMessage', () => {
  it('returns false for assistant messages', () => {
    const msg: Message = { role: 'assistant', content: [{ type: 'tool_result' as const, tool_use_id: '1', content: 'ok' }] };
    expect(isToolResultOnlyMessage(msg)).toBe(false);
  });

  it('returns false for string content', () => {
    const msg: Message = { role: 'user', content: 'hello' };
    expect(isToolResultOnlyMessage(msg)).toBe(false);
  });

  it('returns false for empty array', () => {
    const msg: Message = { role: 'user', content: [] };
    expect(isToolResultOnlyMessage(msg)).toBe(false);
  });

  it('returns true for user message with only tool_result blocks', () => {
    const msg: Message = {
      role: 'user',
      content: [
        { type: 'tool_result' as const, tool_use_id: '1', content: 'ok' },
        { type: 'tool_result' as const, tool_use_id: '2', content: 'done' },
      ],
    };
    expect(isToolResultOnlyMessage(msg)).toBe(true);
  });

  it('returns false for user message with text AND tool_result blocks', () => {
    const msg: Message = {
      role: 'user',
      content: [
        { type: 'text' as const, text: 'User said something' },
        { type: 'tool_result' as const, tool_use_id: '1', content: 'ok' },
      ],
    };
    expect(isToolResultOnlyMessage(msg)).toBe(false);
  });

  it('returns false for user message with only text blocks', () => {
    const msg: Message = {
      role: 'user',
      content: [{ type: 'text' as const, text: 'hello' }],
    };
    expect(isToolResultOnlyMessage(msg)).toBe(false);
  });
});
