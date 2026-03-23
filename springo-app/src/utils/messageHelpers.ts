import type { Message, ContentBlock } from '@/types';

/** Extract readable text from message content (string or ContentBlock[]). */
export function extractTextContent(content: string | ContentBlock[] | undefined): string {
  if (!content) return '';
  if (typeof content === 'string') return content;
  if (Array.isArray(content)) {
    return content
      .map((c) => {
        if (typeof c === 'string') return c;
        if (c.type === 'text') return c.text || '';
        if (c.type === 'image') return '[Image]';
        if (c.type === 'tool_use') return '';
        if (c.type === 'tool_result') return '';
        return '';
      })
      .filter(Boolean)
      .join('\n');
  }
  return '';
}

/** Check if a user message only contains tool_result blocks. */
export function isToolResultOnlyMessage(m: Message): boolean {
  if (m.role !== 'user') return false;
  if (!Array.isArray(m.content)) return false;
  const blocks = m.content as ContentBlock[];
  return blocks.length > 0 && blocks.every((c) => c.type === 'tool_result');
}
