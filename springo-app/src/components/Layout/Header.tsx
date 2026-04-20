import { useSessionStore } from '@/stores/sessionStore';
import { useUIStore } from '@/stores/uiStore';

export default function Header() {
  const toggleSidebar = useUIStore((s) => s.toggleSidebar);

  const currentSessionId = useSessionStore((s) => s.currentSessionId);
  const session = useSessionStore((s) =>
    s.sessions.find((sess) => sess.id === s.currentSessionId),
  );

  const headerTitle =
    currentSessionId && session?.title ? session.title : 'New Chat';

  return (
    <div className="header">
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
        <button
          className="sidebar-toggle"
          onClick={toggleSidebar}
          title="Toggle sidebar"
        >
          <svg
            width="18"
            height="18"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
          >
            <path d="M3 6h12M3 12h12" />
          </svg>
        </button>
        <span className="header-title" id="header-title">
          {headerTitle}
        </span>
      </div>
    </div>
  );
}
