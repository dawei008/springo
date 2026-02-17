import { useRef, useEffect, useMemo, useState, useCallback } from 'react';
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
  const [showScrollBtn, setShowScrollBtn] = useState(false);
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

  // Track scroll position to show/hide scroll-to-bottom button
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const handleScroll = () => {
      const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
      setShowScrollBtn(distanceFromBottom > 300);
    };
    el.addEventListener('scroll', handleScroll, { passive: true });
    return () => el.removeEventListener('scroll', handleScroll);
  }, []);

  const scrollToBottom = useCallback(() => {
    if (containerRef.current) {
      containerRef.current.scrollTo({ top: containerRef.current.scrollHeight, behavior: 'smooth' });
    }
  }, []);

  const hasMessages = messages.length > 0 && !messages.every((m) => m.isThinking);

  return (
    <div className="chat-container" ref={containerRef}>
      <div className="chat-content">
        {hasMessages ? <MessageList messages={messages} /> : <WelcomeScreen />}
      </div>
      {toolPanelOpen && <ToolPanel />}
      {showScrollBtn && (
        <button
          className="scroll-to-bottom-btn"
          onClick={scrollToBottom}
          title="Scroll to bottom"
          style={{
            position: 'absolute',
            bottom: 16,
            right: 24,
            width: 36,
            height: 36,
            borderRadius: '50%',
            border: '1px solid var(--border)',
            background: 'var(--bg-primary)',
            color: 'var(--text-secondary)',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            boxShadow: '0 2px 8px rgba(0,0,0,0.15)',
            zIndex: 10,
            transition: 'opacity 0.2s',
          }}
        >
          <svg width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
            <path d="M7 13l5 5 5-5M7 6l5 5 5-5" />
          </svg>
        </button>
      )}
    </div>
  );
}
