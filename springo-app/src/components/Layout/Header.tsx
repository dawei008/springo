import { useSessionStore } from '@/stores/sessionStore';

export default function Header() {
  const currentSessionId = useSessionStore((s) => s.currentSessionId);
  const session = useSessionStore((s) =>
    s.sessions.find((sess) => sess.id === s.currentSessionId),
  );

  const headerTitle =
    currentSessionId && session?.title ? session.title : 'New Chat';

  return (
    <div className="header">
      <span className="header-title" id="header-title">
        {headerTitle}
      </span>
    </div>
  );
}
