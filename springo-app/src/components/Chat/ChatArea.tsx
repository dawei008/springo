import { useRef, useEffect, useMemo } from 'react';
import { useSessionStore } from '@/stores/sessionStore';
import { useChatStore } from '@/stores/chatStore';
import WelcomeScreen from './WelcomeScreen';
import MessageList from './MessageList';
import ToolPanel from './ToolPanel';
import { useUIStore } from '@/stores/uiStore';
import type { Message } from '@/types';

const EMPTY_MESSAGES: Message[] = [];

export default function ChatArea() {
  const containerRef = useRef<HTMLDivElement>(null);
  const currentSessionId = useSessionStore((s) => s.currentSessionId);
  const runtimes = useChatStore((s) => s.runtimes);
  const toolPanelOpen = useUIStore((s) => s.toolPanelOpen);

  const messages = useMemo(() => {
    if (!currentSessionId) return EMPTY_MESSAGES;
    return runtimes[currentSessionId]?.messages ?? EMPTY_MESSAGES;
  }, [currentSessionId, runtimes]);

  // Load messages when switching sessions
  useEffect(() => {
    if (currentSessionId) {
      const runtime = useChatStore.getState().runtimes[currentSessionId];
      if (!runtime || runtime.messages.length === 0) {
        // Load from backend
        const loadFromBackend = async () => {
          try {
            const res = await fetch(`http://127.0.0.1:8081/v1/sessions/${currentSessionId}`);
            if (res.ok) {
              const data = await res.json();
              const loadedMessages = data.messages || [];
              if (loadedMessages.length > 0) {
                const { getRuntime } = useChatStore.getState();
                const rt = getRuntime(currentSessionId);
                rt.messages = loadedMessages;
                // Trigger re-render
                useChatStore.setState((s) => ({
                  runtimes: { ...s.runtimes, [currentSessionId]: { ...rt } },
                }));
              }
            }
          } catch (e) {
            console.error('Failed to load session messages:', e);
          }
        };
        loadFromBackend();
      }
    }
  }, [currentSessionId]);

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    if (containerRef.current) {
      const el = containerRef.current;
      const isNearBottom =
        el.scrollHeight - el.scrollTop - el.clientHeight < 150;
      if (isNearBottom) {
        requestAnimationFrame(() => {
          el.scrollTop = el.scrollHeight;
        });
      }
    }
  }, [messages]);

  const hasMessages = messages.length > 0 && !messages.every((m) => m.isThinking);

  return (
    <div className="chat-container" ref={containerRef}>
      <div className="chat-content">
        {hasMessages ? <MessageList messages={messages} /> : <WelcomeScreen />}
      </div>
      {toolPanelOpen && <ToolPanel />}
    </div>
  );
}
