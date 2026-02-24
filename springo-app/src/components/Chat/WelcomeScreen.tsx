import { useEffect, useMemo } from 'react';
import { useToolsStore } from '@/stores/toolsStore';

// ---------------------------------------------------------------------------
// SVG Icons (stroke-based, consistent with existing UI)
// ---------------------------------------------------------------------------
const Icon = {
  document: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" />
      <polyline points="14 2 14 8 20 8" />
      <line x1="16" y1="13" x2="8" y2="13" />
      <line x1="16" y1="17" x2="8" y2="17" />
    </svg>
  ),
  search: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="11" cy="11" r="8" />
      <line x1="21" y1="21" x2="16.65" y2="16.65" />
    </svg>
  ),
  diagram: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="3" width="7" height="7" rx="1" />
      <rect x="14" y="3" width="7" height="7" rx="1" />
      <rect x="14" y="14" width="7" height="7" rx="1" />
      <line x1="10" y1="6.5" x2="14" y2="6.5" />
      <line x1="17.5" y1="10" x2="17.5" y2="14" />
    </svg>
  ),
  video: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <polygon points="23 7 16 12 23 17 23 7" />
      <rect x="1" y="5" width="15" height="14" rx="2" ry="2" />
    </svg>
  ),
  github: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M9 19c-5 1.5-5-2.5-7-3m14 6v-3.87a3.37 3.37 0 00-.94-2.61c3.14-.35 6.44-1.54 6.44-7A5.44 5.44 0 0020 4.77 5.07 5.07 0 0019.91 1S18.73.65 16 2.48a13.38 13.38 0 00-7 0C6.27.65 5.09 1 5.09 1A5.07 5.07 0 005 4.77a5.44 5.44 0 00-1.5 3.78c0 5.42 3.3 6.61 6.44 7A3.37 3.37 0 009 18.13V22" />
    </svg>
  ),
  cloud: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M18 10h-1.26A8 8 0 109 20h9a5 5 0 000-10z" />
    </svg>
  ),
  browser: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <rect x="2" y="3" width="20" height="14" rx="2" ry="2" />
      <line x1="8" y1="21" x2="16" y2="21" />
      <line x1="12" y1="17" x2="12" y2="21" />
    </svg>
  ),
  memory: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10" />
      <polyline points="12 6 12 12 16 14" />
    </svg>
  ),
  code: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="16 18 22 12 16 6" />
      <polyline points="8 6 2 12 8 18" />
    </svg>
  ),
  team: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2" />
      <circle cx="9" cy="7" r="4" />
      <path d="M23 21v-2a4 4 0 00-3-3.87" />
      <path d="M16 3.13a4 4 0 010 7.75" />
    </svg>
  ),
};

// ---------------------------------------------------------------------------
// Capability definitions — matched against live skills & MCP servers
// ---------------------------------------------------------------------------
interface CapabilityDef {
  id: string;
  icon: React.ReactNode;
  title: string;
  description: string;
  prompt: string;
  matchSkills?: string[];
  matchServers?: string[];
  alwaysShow?: boolean;
}

const CAPABILITY_DEFS: CapabilityDef[] = [
  {
    id: 'documents',
    icon: Icon.document,
    title: 'Documents & Sheets',
    description: 'Create and edit PDFs, Word, Excel, presentations',
    prompt: 'Help me create a professional document',
    matchSkills: ['pdf', 'docx', 'xlsx', 'pptx', 'aws-pptx'],
  },
  {
    id: 'web-search',
    icon: Icon.search,
    title: 'Web Search',
    description: 'Search the web, read articles, find answers',
    prompt: 'Search the web for ',
    matchServers: ['web-search', 'fetch'],
  },
  {
    id: 'diagrams',
    icon: Icon.diagram,
    title: 'Diagrams & Design',
    description: 'Draw architecture diagrams, flowcharts, wireframes',
    prompt: 'Help me draw a system architecture diagram for ',
    matchServers: ['excalidraw', 'drawio', 'pencil', 'aws-diagram'],
  },
  {
    id: 'video',
    icon: Icon.video,
    title: 'Video Editing',
    description: 'Clip YouTube videos with bilingual subtitles',
    prompt: 'Help me clip a YouTube video: ',
    matchSkills: ['youtube-clipper'],
  },
  {
    id: 'github',
    icon: Icon.github,
    title: 'GitHub',
    description: 'Browse repos, issues, and pull requests',
    prompt: 'Show my recent GitHub activity',
    matchServers: ['github'],
  },
  {
    id: 'aws',
    icon: Icon.cloud,
    title: 'AWS Assistant',
    description: 'Pricing lookup, architecture advice, documentation',
    prompt: 'Help me estimate AWS costs for ',
    matchServers: ['aws-pricing', 'aws-knowledge', 'bedrock-agentcore'],
  },
  {
    id: 'browser',
    icon: Icon.browser,
    title: 'Browser Automation',
    description: 'Navigate websites, fill forms, take screenshots',
    prompt: 'Open a browser and navigate to ',
    matchServers: ['playwright'],
    matchSkills: ['browser-use'],
  },
  {
    id: 'memory',
    icon: Icon.memory,
    title: 'Memory',
    description: 'Remember your preferences across sessions',
    prompt: 'What do you remember about our previous conversations?',
    matchSkills: ['memory'],
  },
  {
    id: 'code',
    icon: Icon.code,
    title: 'Code Assistant',
    description: 'Analyze code, review PRs, explain any codebase',
    prompt: 'Analyze the code in the current working directory',
    alwaysShow: true,
  },
  {
    id: 'team',
    icon: Icon.team,
    title: 'Multi-Agent Teams',
    description: 'Enable Team Mode for complex parallel tasks',
    prompt: 'Help me with a complex task. Use team mode to work on it in parallel.',
    alwaysShow: true,
  },
];

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------
export default function WelcomeScreen() {
  const { skills, mcpServers, fetchAll } = useToolsStore();

  useEffect(() => {
    if (skills.length === 0 && mcpServers.length === 0) {
      fetchAll();
    }
  }, [skills.length, mcpServers.length, fetchAll]);

  const { capabilities, matchedTools } = useMemo(() => {
    const skillNames = new Set(skills.map((s) => s.name));
    const serverNames = new Set(mcpServers.map((s) => s.name));

    const matches: Record<string, string[]> = {};

    const caps = CAPABILITY_DEFS.filter((cap) => {
      const matched: string[] = [];

      if (cap.matchSkills) {
        for (const skill of cap.matchSkills) {
          if (skillNames.has(skill)) {
            matched.push(skill);
          }
        }
      }

      if (cap.matchServers) {
        for (const server of cap.matchServers) {
          if (serverNames.has(server)) {
            matched.push(server);
          }
        }
      }

      matches[cap.id] = matched;
      return cap.alwaysShow || matched.length > 0;
    }).slice(0, 6);

    return { capabilities: caps, matchedTools: matches };
  }, [skills, mcpServers]);

  const totalTools = mcpServers.reduce(
    (sum, s) => sum + Math.max(s.tools || 0, s.cached_tools || 0),
    0,
  );

  const handlePromptClick = (text: string) => {
    const input = document.getElementById('message-input') as HTMLTextAreaElement | null;
    if (input) {
      const nativeInputValueSetter = Object.getOwnPropertyDescriptor(
        window.HTMLTextAreaElement.prototype,
        'value',
      )?.set;
      if (nativeInputValueSetter) {
        nativeInputValueSetter.call(input, text);
        input.dispatchEvent(new Event('input', { bubbles: true }));
      }
      input.focus();
    }
  };

  return (
    <div className="welcome" id="welcome">
      <div className="welcome-glow" />
      <svg
        className="welcome-icon"
        viewBox="0 0 100 100"
        fill="none"
        stroke="currentColor"
        strokeWidth="2.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <ellipse cx="50" cy="38" rx="22" ry="20" />
        <path d="M28 35 C15 38, 8 55, 12 72 C14 78, 18 80, 22 78 C28 75, 30 65, 30 55" />
        <path d="M72 35 C85 38, 92 55, 88 72 C86 78, 82 80, 78 78 C72 75, 70 65, 70 55" />
        <circle cx="40" cy="35" r="3" fill="currentColor" />
        <circle cx="60" cy="35" r="3" fill="currentColor" />
        <ellipse cx="50" cy="48" rx="5" ry="4" fill="currentColor" />
        <path d="M45 52 Q50 58, 55 52" />
        <path d="M35 56 Q50 65, 65 56" />
      </svg>
      <h1>Springo</h1>
      {skills.length > 0 || mcpServers.length > 0 ? (
        <p>
          {skills.length} skills &middot; {totalTools} tools &middot; {mcpServers.length} servers
        </p>
      ) : (
        <p>Your AI assistant</p>
      )}
      <div className="welcome-prompts">
        {capabilities.map((cap, idx) => (
          <div
            key={cap.id}
            className="welcome-prompt"
            onClick={() => handlePromptClick(cap.prompt)}
            style={{ animationDelay: `${idx * 80 + 200}ms` }}
          >
            <div className="welcome-prompt-icon">{cap.icon}</div>
            <div className="welcome-prompt-text">
              <h3>{cap.title}</h3>
              <p>{cap.description}</p>
              {matchedTools[cap.id]?.length > 0 && (
                <div className="welcome-prompt-tags">
                  {matchedTools[cap.id].map((t) => (
                    <span key={t} className="welcome-prompt-tag">
                      {t}
                    </span>
                  ))}
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
