import { useEffect, useMemo, useState } from 'react';
import { useToolsStore } from '@/stores/toolsStore';
import { useSessionStore } from '@/stores/sessionStore';
import { useSettingsStore } from '@/stores/settingsStore';

const SEEN_KEY = 'springo-seen-capabilities';

function getSeenSet(): Set<string> {
  try {
    const raw = localStorage.getItem(SEEN_KEY);
    return raw ? new Set(JSON.parse(raw)) : new Set();
  } catch { return new Set(); }
}

function markSeen(names: string[]) {
  const seen = getSeenSet();
  for (const n of names) seen.add(n);
  localStorage.setItem(SEEN_KEY, JSON.stringify([...seen]));
}

function WhatsNew() {
  const skills = useToolsStore((s) => s.skills);
  const mcpServers = useToolsStore((s) => s.mcpServers);
  const [newItems, setNewItems] = useState<{ type: string; name: string; desc: string }[]>([]);

  useEffect(() => {
    if (skills.length === 0 && mcpServers.length === 0) return;
    const seen = getSeenSet();
    const items: { type: string; name: string; desc: string }[] = [];

    for (const s of skills) {
      if (!seen.has(`skill:${s.name}`)) {
        items.push({ type: 'skill', name: s.name, desc: s.description || '' });
      }
    }
    for (const s of mcpServers) {
      if (!seen.has(`server:${s.name}`)) {
        items.push({ type: 'server', name: s.name, desc: s.description || `${Math.max(s.tools || 0, s.cached_tools || 0)} tools` });
      }
    }

    setNewItems(items.slice(0, 5));

    const allNames = [
      ...skills.map((s) => `skill:${s.name}`),
      ...mcpServers.map((s) => `server:${s.name}`),
    ];
    markSeen(allNames);
  }, [skills, mcpServers]);

  if (newItems.length === 0) return null;

  return (
    <div className="welcome-section">
      <div className="welcome-section-title">What's New</div>
      {newItems.map((item) => (
        <div key={`${item.type}:${item.name}`} className="welcome-row">
          {item.type === 'skill' ? (
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>
            </svg>
          ) : (
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <rect x="2" y="2" width="20" height="8" rx="2"/>
              <rect x="2" y="14" width="20" height="8" rx="2"/>
              <line x1="6" y1="6" x2="6.01" y2="6"/>
              <line x1="6" y1="18" x2="6.01" y2="18"/>
            </svg>
          )}
          <span className="welcome-row-label">{item.name}</span>
          <span className="welcome-row-meta">{item.type}</span>
        </div>
      ))}
    </div>
  );
}

function RecentSessions() {
  const sessions = useSessionStore((s) => s.sessions);
  const switchSession = useSessionStore((s) => s.switchSession);

  const recent = useMemo(() => {
    return sessions
      .filter((s) => s.title && s.title !== 'New Chat')
      .slice(0, 3);
  }, [sessions]);

  if (recent.length === 0) return null;

  return (
    <div className="welcome-section">
      <div className="welcome-section-title">Recent</div>
      {recent.map((s) => (
        <div
          key={s.id}
          className="welcome-row clickable"
          onClick={() => switchSession(s.id)}
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
          </svg>
          <span className="welcome-row-label">{s.title}</span>
          <span className="welcome-row-meta">
            {formatRelativeTime(s.updatedAt || s.createdAt || 0)}
          </span>
        </div>
      ))}
    </div>
  );
}

function formatRelativeTime(ts: number): string {
  if (!ts) return '';
  const diff = Date.now() - ts;
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

export default function WelcomeScreen() {
  const { skills, mcpServers, fetchAll } = useToolsStore();
  const workingDir = useSettingsStore((s) => s.workingDir);

  useEffect(() => {
    if (skills.length === 0 && mcpServers.length === 0) {
      fetchAll();
    }
  }, [skills.length, mcpServers.length, fetchAll]);

  const hour = new Date().getHours();
  const greeting =
    hour < 12 ? 'Good morning' : hour < 18 ? 'Good afternoon' : 'Good evening';

  const dirName = workingDir ? workingDir.replace(/^\/Users\/[^/]+/, '~') : '';

  return (
    <div className="welcome" id="welcome">
      <div className="welcome-center">
        <h1 className="welcome-greeting">{greeting}.</h1>
        <p className="welcome-sub">How can I help you today?</p>
      </div>

      <div className="welcome-info">
        {dirName && (
          <div className="welcome-section">
            <div className="welcome-section-title">Workspace</div>
            <div className="welcome-row">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7z"/>
              </svg>
              <span className="welcome-row-label">{dirName}</span>
            </div>
          </div>
        )}

        <WhatsNew />

        <RecentSessions />
      </div>
    </div>
  );
}
