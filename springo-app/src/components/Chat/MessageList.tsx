import { useMemo } from 'react';
import Message from './Message';
import type { DisplayMessage } from './Message';
import type { Message as MessageType, ContentBlock, ToolUseBlock, ToolUse } from '@/types';
import { extractTextContent, isToolResultOnlyMessage } from '@/utils/messageHelpers';

interface Props {
  messages: MessageType[];
  isStreaming?: boolean;
}

export default function MessageList({ messages, isStreaming = false }: Props) {
  const displayMessages = useMemo(() => {
    // Filter out internal messages for display
    const filtered = messages.filter((m, idx) => {
      // Skip user messages that contain tool_result blocks
      if (isToolResultOnlyMessage(m)) {
        return false;
      }
      // Skip assistant messages that only have tool_use (no text),
      // but don't skip the last message (active streaming message)
      if (m.role === 'assistant' && m.hasToolUse && idx < messages.length - 1) {
        const display = m.displayContent || extractTextContent(m.content);
        if (!display.trim()) return false;
      }
      // Skip thinking indicators
      if (m.isThinking) return false;
      return true;
    });

    // Merge consecutive assistant messages for display
    // BUT don't merge delegation result messages - they should stay separate
    const result: DisplayMessage[] = [];
    for (const m of filtered) {
      const last = result[result.length - 1];
      const shouldMerge =
        m.role === 'assistant' &&
        last?.role === 'assistant' &&
        !m.isDelegationResult &&
        !last.isDelegationResult &&
        !m.isTaskResult &&
        !last.isTaskResult &&
        !m.askUser &&
        !last.askUser &&
        !m._teamChat &&
        !last._teamChat;

      if (shouldMerge) {
        // Merge with previous assistant message - extract text properly
        const prevContent =
          last.mergedContent ||
          extractTextContent(last.displayContent as string | undefined) ||
          extractTextContent(last.content);
        const currContent =
          extractTextContent(m.displayContent as string | undefined) ||
          extractTextContent(m.content);
        if (currContent) {
          last.mergedContent = prevContent + '\n\n' + currContent;
        }
        // Accumulate tool_use blocks from merged messages for consolidated tool panel.
        // After backend sync, each assistant message has 1-2 tool_use blocks in content.
        // Without this, only the first (merge base) message's tools would be displayed.
        const currTools: ToolUse[] = m.toolUses && m.toolUses.length > 0
          ? m.toolUses
          : Array.isArray(m.content)
            ? (m.content as ContentBlock[])
                .filter((c): c is ToolUseBlock => c.type === 'tool_use')
                .map((tb) => ({ id: tb.id, name: tb.name, input: tb.input || {}, status: 'complete' as const }))
            : [];
        if (currTools.length > 0) {
          if (!last.toolUses || last.toolUses.length === 0) {
            // First tool merge: also include base message's own tools
            const baseTools: ToolUse[] = Array.isArray(last.content)
              ? (last.content as ContentBlock[])
                  .filter((c): c is ToolUseBlock => c.type === 'tool_use')
                  .map((tb) => ({ id: tb.id, name: tb.name, input: tb.input || {}, status: 'complete' as const }))
              : [];
            last.toolUses = [...baseTools, ...currTools];
          } else {
            // Subsequent merges: append new tools, skip duplicates by ID
            const existingIds = new Set(last.toolUses.map((t) => t.id));
            const newTools = currTools.filter((t) => !existingIds.has(t.id));
            if (newTools.length > 0) {
              last.toolUses = [...last.toolUses, ...newTools];
            }
          }
          last.hasToolUse = true;
        }
      } else {
        // Add new message (clone to avoid modifying original)
        result.push({ ...m });
      }
    }

    return result;
  }, [messages]);

  // Only the last assistant message shows the tool panel.
  const lastAssistantIdx = useMemo(() => {
    for (let i = displayMessages.length - 1; i >= 0; i--) {
      if (displayMessages[i].role === 'assistant') return i;
    }
    return -1;
  }, [displayMessages]);

  return (
    <>
      {displayMessages.map((msg, i) => (
        <Message
          key={`${msg.role}-${msg.timestamp ?? i}`}
          message={msg}
          showToolPanel={i === lastAssistantIdx}
          isStreaming={i === lastAssistantIdx ? isStreaming : false}
        />
      ))}
    </>
  );
}
