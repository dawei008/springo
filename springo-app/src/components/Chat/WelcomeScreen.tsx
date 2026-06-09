import { useEffect, useMemo, useState } from 'react';
import { useToolsStore } from '@/stores/toolsStore';
import { useSessionStore } from '@/stores/sessionStore';
import { useSettingsStore } from '@/stores/settingsStore';
import { DEFAULT_SESSION_TITLES } from '@/utils/cleanupSuggestions';

function SessionModeIconSmall({ mode }: { mode?: string }) {
  const props = { width: '14', height: '14', viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: '2', strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const };
  switch (mode) {
    case 'design':
      return <svg {...props}><circle cx="13.5" cy="6.5" r="2.5"/><path d="M17 2h2a2 2 0 0 1 2 2v2"/><path d="M2 17v2a2 2 0 0 0 2 2h2"/><circle cx="10.5" cy="17.5" r="2.5"/><path d="M2 7V4a2 2 0 0 1 2-2h3"/><path d="M22 17v3a2 2 0 0 1-2 2h-3"/></svg>;
    case 'plan':
      return <svg {...props}><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>;
    case 'team':
      return <svg {...props}><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>;
    case 'meeting':
      return <svg {...props}><rect x="9" y="2" width="6" height="12" rx="3"/><path d="M5 10a7 7 0 0 0 14 0"/><line x1="12" y1="19" x2="12" y2="22"/></svg>;
    case 'recording':
      return <svg {...props}><rect x="2" y="3" width="20" height="14" rx="2"/><circle cx="12" cy="10" r="3"/></svg>;
    default:
      return <svg {...props}><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>;
  }
}

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
      .filter((s) => s.title && !DEFAULT_SESSION_TITLES.has(s.title))
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
          <SessionModeIconSmall mode={s.mode} />
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
