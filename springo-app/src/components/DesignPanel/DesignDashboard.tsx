import { useState, useMemo, useCallback } from 'react';
import { useSessionStore } from '@/stores/sessionStore';
import { useSettingsStore } from '@/stores/settingsStore';
import { useChatStore } from '@/stores/chatStore';
import { useDesignStore } from '@/stores/designStore';
import { DESIGN_TEMPLATES, TEMPLATE_CATEGORIES, type DesignTemplate } from '@/data/designTemplates';
import type { DesignSystemConfig } from '@/types';

type DashboardTab = 'recent' | 'examples' | 'design-systems';
type CreatorType = 'prototype' | 'slides' | 'template';

const PRESET_DESIGN_SYSTEMS: (DesignSystemConfig & { id: string; description: string })[] = [
  {
    id: 'material',
    brandName: 'Material Design',
    description: 'Google\'s design system — clean, bold, colorful',
    colors: { primary: '#1976D2', secondary: '#9C27B0', error: '#D32F2F', surface: '#FFFFFF', background: '#FAFAFA', text: '#212121' },
    fonts: { heading: 'Roboto', body: 'Roboto' },
    components: ['Button', 'Card', 'TextField', 'AppBar', 'Chip', 'Dialog', 'Snackbar', 'FAB'],
  },
  {
    id: 'apple-hig',
    brandName: 'Apple HIG',
    description: 'iOS/macOS style — SF Pro, subtle shadows, vibrancy',
    colors: { primary: '#007AFF', secondary: '#5856D6', success: '#34C759', warning: '#FF9500', danger: '#FF3B30', background: '#F2F2F7', text: '#000000' },
    fonts: { heading: 'SF Pro Display', body: 'SF Pro Text' },
    components: ['NavigationBar', 'TabBar', 'ActionSheet', 'Alert', 'Toggle', 'Segmented Control'],
  },
  {
    id: 'shadcn',
    brandName: 'shadcn/ui',
    description: 'Minimal, composable — Tailwind + Radix based',
    colors: { primary: '#18181B', secondary: '#71717A', accent: '#F4F4F5', border: '#E4E4E7', background: '#FFFFFF', foreground: '#09090B' },
    fonts: { heading: 'Inter', body: 'Inter' },
    components: ['Button', 'Card', 'Input', 'Dialog', 'Dropdown', 'Toast', 'Table', 'Badge'],
  },
  {
    id: 'glassmorphism',
    brandName: 'Glassmorphism',
    description: 'Frosted glass, blur effects, gradients',
    colors: { primary: '#667EEA', secondary: '#764BA2', accent: '#F093FB', surface: 'rgba(255,255,255,0.15)', background: '#0F0C29', text: '#FFFFFF' },
    fonts: { heading: 'Poppins', body: 'Inter' },
    components: ['GlassCard', 'BlurPanel', 'GradientButton', 'FloatingNav'],
  },
  {
    id: 'retro',
    brandName: 'Retro / Neubrutalism',
    description: 'Bold borders, chunky shadows, bright palette',
    colors: { primary: '#FF6B6B', secondary: '#4ECDC4', accent: '#FFE66D', background: '#F7FFF7', text: '#2C3E50', border: '#2C3E50' },
    fonts: { heading: 'Space Grotesk', body: 'DM Sans' },
    components: ['BrutalCard', 'ChunkyButton', 'RetroInput', 'StickerBadge'],
  },
  {
    id: 'corporate',
    brandName: 'Corporate / Enterprise',
    description: 'Professional, accessible, data-dense layouts',
    colors: { primary: '#1B365D', secondary: '#4A90D9', success: '#2E7D32', warning: '#F57C00', neutral: '#78909C', background: '#FAFBFC', text: '#1A1A2E' },
    fonts: { heading: 'Inter', body: 'Source Sans Pro' },
    components: ['DataTable', 'Dashboard', 'Sidebar', 'KPICard', 'Chart', 'Breadcrumb'],
  },
];

const EXAMPLE_PROMPTS = [
  {
    id: 'ex-calculator',
    name: 'Calculator',
    category: 'interactive',
    description: 'iOS-style calculator with working arithmetic',
    prompt: 'Design a beautiful iOS-style calculator app with working arithmetic operations. Include a display, number pad, and operation buttons (+, -, ×, ÷, =). Use a dark theme with orange accent for operators. Make all buttons functional.',
    tags: ['interactive', 'mobile'],
  },
  {
    id: 'ex-weather',
    name: 'Weather App',
    category: 'data',
    description: 'Weather dashboard with forecast cards and animated icons',
    prompt: 'Design a weather app showing current conditions (temperature, humidity, wind, UV index), a 7-day forecast with animated weather icons (sun, clouds, rain), and an hourly temperature chart. Use a gradient background that changes with conditions.',
    tags: ['data', 'mobile'],
  },
  {
    id: 'ex-ecommerce',
    name: 'E-Commerce Store',
    category: 'web',
    description: 'Product listing with filters, cart, and checkout flow',
    prompt: 'Design an e-commerce storefront with a product grid (8 products with images, prices, ratings), sidebar filters (category, price range, rating), a shopping cart drawer that slides in from the right with item count badge, and a mini checkout form.',
    tags: ['web', 'interactive'],
  },
  {
    id: 'ex-dashboard',
    name: 'Analytics Dashboard',
    category: 'data',
    description: 'Real-time analytics with charts, KPIs, and data tables',
    prompt: 'Design a real-time analytics dashboard with: 4 KPI cards (Revenue, Users, Conversion, Avg Order), a line chart showing 30-day trend, a donut chart for traffic sources, a sortable data table with 10 rows, and a sidebar navigation. Use a clean professional theme.',
    tags: ['data', 'web'],
  },
  {
    id: 'ex-social',
    name: 'Social Feed',
    category: 'interactive',
    description: 'Social media feed with posts, likes, and comments',
    prompt: 'Design a social media feed with: post cards (avatar, username, timestamp, text, image, like/comment/share buttons with counts), a story bar at the top with circular avatars, a compose post modal, and infinite scroll simulation. Make like buttons toggle.',
    tags: ['interactive', 'mobile'],
  },
  {
    id: 'ex-portfolio',
    name: 'Portfolio Site',
    category: 'web',
    description: 'Developer portfolio with projects, skills, and contact',
    prompt: 'Design a developer portfolio single-page site with: hero section with animated gradient text, project showcase grid with hover effects, skills section with progress bars, testimonials carousel, and a contact form. Use smooth scroll navigation.',
    tags: ['web'],
  },
  {
    id: 'ex-music',
    name: 'Music Player',
    category: 'interactive',
    description: 'Spotify-like music player with playlists and controls',
    prompt: 'Design a music player interface like Spotify with: left sidebar (playlists, library), main area (album art, track list), and a bottom playback bar with play/pause/skip/shuffle controls, progress slider, and volume control. Include a "Now Playing" album art animation.',
    tags: ['interactive'],
  },
  {
    id: 'ex-iridescent',
    name: 'Iridescent Card',
    category: 'creative',
    description: 'Playing card with 3D perspective and iridescent glow',
    prompt: 'Create a monochromatic playing card. Display it on the page with a rich perspective hover effect and glow. The bright areas should be iridescent; there should be a subtle noise texture and specular glow that reacts to the mouse position. Add tweaks for as many aspects of this effect as you can.',
    tags: ['creative', 'interactive'],
  },
];

function formatRelativeTime(ts: number): string {
  if (!ts) return '';
  const diff = Date.now() - ts;
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}d ago`;
  return `${Math.floor(days / 30)}mo ago`;
}

function ProjectCard({ session, onClick }: { session: { id: string; title: string; updatedAt: number; mode?: string }; onClick: () => void }) {
  return (
    <div className="design-dash-card" onClick={onClick}>
      <div className="design-dash-card-thumb">
        <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1" opacity="0.2">
          <rect x="3" y="3" width="18" height="18" rx="2" />
          <circle cx="8.5" cy="8.5" r="1.5" />
          <path d="M21 15l-5-5L5 21" />
        </svg>
      </div>
      <div className="design-dash-card-info">
        <div className="design-dash-card-title">{session.title}</div>
        <div className="design-dash-card-meta">{formatRelativeTime(session.updatedAt)}</div>
      </div>
    </div>
  );
}

function ExampleCard({ example, onUse }: { example: typeof EXAMPLE_PROMPTS[0]; onUse: () => void }) {
  return (
    <div className="design-dash-example">
      <div className="design-dash-example-header">
        <span className="design-dash-example-name">{example.name}</span>
        <div className="design-dash-example-tags">
          {example.tags.map((t) => <span key={t} className="design-dash-tag">{t}</span>)}
        </div>
      </div>
      <p className="design-dash-example-desc">{example.description}</p>
      <button className="design-dash-use-btn" onClick={onUse}>Use this prompt</button>
    </div>
  );
}

export default function DesignDashboard() {
  const [tab, setTab] = useState<DashboardTab>('recent');
  const [creatorType, setCreatorType] = useState<CreatorType>('prototype');
  const [projectName, setProjectName] = useState('');
  const [fidelity, setFidelity] = useState<'wireframe' | 'high'>('high');
  const [templateFilter, setTemplateFilter] = useState<string>('all');
  const [searchQuery, setSearchQuery] = useState('');

  const sessions = useSessionStore((s) => s.sessions);
  const switchSession = useSessionStore((s) => s.switchSession);
  const designSystem = useDesignStore((s) => s.designSystem);

  const designSessions = useMemo(() => {
    return sessions.filter((s) => s.mode === 'design').slice(0, 20);
  }, [sessions]);

  const filteredSessions = useMemo(() => {
    if (!searchQuery) return designSessions;
    const q = searchQuery.toLowerCase();
    return designSessions.filter((s) => s.title.toLowerCase().includes(q));
  }, [designSessions, searchQuery]);

  const handleCreateProject = useCallback(() => {
    const title = projectName.trim() || 'New Design';
    const id = useSessionStore.getState().createSession(title, 'design');
    const settings = useSettingsStore.getState().settings;
    const ds = useDesignStore.getState().designSystem;

    const fidelityHint = fidelity === 'wireframe'
      ? 'Create a LOW-FIDELITY WIREFRAME using only grayscale colors, simple shapes, and placeholder text. No colors, no detailed styling.'
      : 'Create a HIGH-FIDELITY design with polished visuals, colors, shadows, and production-ready styling.';

    const prompt = `${fidelityHint}\n\nDesign: ${title}`;

    useChatStore.getState().sendMessage(id, prompt, [], {
      model: settings.model,
      maxTokens: settings.maxTokens,
      temperature: settings.temperature,
      systemPrompt: settings.systemPrompt,
      compactModel: settings.compactModel,
      sessionId: id,
      designMode: true,
      designSystem: ds || undefined,
    });
    setProjectName('');
  }, [projectName, fidelity]);

  const handleUsePrompt = useCallback((prompt: string) => {
    const id = useSessionStore.getState().createSession(undefined, 'design');
    const settings = useSettingsStore.getState().settings;
    const ds = useDesignStore.getState().designSystem;

    useChatStore.getState().sendMessage(id, prompt, [], {
      model: settings.model,
      maxTokens: settings.maxTokens,
      temperature: settings.temperature,
      systemPrompt: settings.systemPrompt,
      compactModel: settings.compactModel,
      sessionId: id,
      designMode: true,
      designSystem: ds || undefined,
    });
  }, []);

  const handleTemplateSelect = useCallback((template: DesignTemplate) => {
    handleUsePrompt(template.prompt);
  }, [handleUsePrompt]);

  const filteredTemplates = useMemo(() => {
    if (templateFilter === 'all') return DESIGN_TEMPLATES;
    return DESIGN_TEMPLATES.filter((t) => t.category === templateFilter);
  }, [templateFilter]);

  return (
    <div className="design-dashboard">
      {/* Left: Project Creator */}
      <aside className="design-dash-creator">
        <div className="design-dash-creator-tabs">
          <button className={`design-dash-creator-tab${creatorType === 'prototype' ? ' active' : ''}`} onClick={() => setCreatorType('prototype')}>Prototype</button>
          <button className={`design-dash-creator-tab${creatorType === 'slides' ? ' active' : ''}`} onClick={() => setCreatorType('slides')}>Slides</button>
          <button className={`design-dash-creator-tab${creatorType === 'template' ? ' active' : ''}`} onClick={() => setCreatorType('template')}>Template</button>
        </div>

        {creatorType !== 'template' ? (
          <div className="design-dash-creator-form">
            <h3 className="design-dash-creator-title">New {creatorType === 'slides' ? 'slide deck' : 'prototype'}</h3>
            <input
              className="design-dash-input"
              placeholder="Project name"
              value={projectName}
              onChange={(e) => setProjectName(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') handleCreateProject(); }}
            />

            {designSystem && (
              <div className="design-dash-ds-picker">
                <div className="design-dash-ds-label">Design system</div>
                <div className="design-dash-ds-item">
                  <div className="design-dash-ds-icon" style={{ background: designSystem.colors?.primary || 'var(--accent)' }} />
                  <div>
                    <div className="design-dash-ds-name">{designSystem.brandName || 'Design System'}</div>
                    <div className="design-dash-ds-meta">Default</div>
                  </div>
                </div>
              </div>
            )}

            <div className="design-dash-fidelity">
              <button
                className={`design-dash-fidelity-option${fidelity === 'wireframe' ? ' active' : ''}`}
                onClick={() => setFidelity('wireframe')}
              >
                <svg width="40" height="30" viewBox="0 0 40 30" fill="none" stroke="currentColor" strokeWidth="1" opacity="0.4">
                  <rect x="2" y="2" width="36" height="26" rx="2" strokeDasharray="3 2" />
                  <circle cx="10" cy="10" r="4" strokeDasharray="2 2" />
                  <line x1="18" y1="8" x2="35" y2="8" strokeDasharray="3 2" />
                  <line x1="18" y1="13" x2="30" y2="13" strokeDasharray="3 2" />
                  <rect x="5" y="20" width="30" height="5" rx="1" strokeDasharray="3 2" />
                </svg>
                <span>Wireframe</span>
              </button>
              <button
                className={`design-dash-fidelity-option${fidelity === 'high' ? ' active' : ''}`}
                onClick={() => setFidelity('high')}
              >
                <svg width="40" height="30" viewBox="0 0 40 30" fill="none">
                  <rect x="2" y="2" width="36" height="26" rx="2" fill="#f3f0ff" stroke="#8b7fff" strokeWidth="1" />
                  <rect x="5" y="5" width="12" height="8" rx="1" fill="#c4b5fd" />
                  <rect x="20" y="5" width="16" height="3" rx="1" fill="#8b7fff" />
                  <rect x="20" y="10" width="10" height="2" rx="1" fill="#ddd6fe" />
                  <rect x="5" y="17" width="31" height="8" rx="2" fill="#8b7fff" />
                </svg>
                <span>High fidelity</span>
              </button>
            </div>

            <button
              className="design-dash-create-btn"
              onClick={handleCreateProject}
            >
              + Create
            </button>
          </div>
        ) : (
          <div className="design-dash-template-list">
            <div className="design-dash-template-filter">
              <button className={`design-dash-tag-btn${templateFilter === 'all' ? ' active' : ''}`} onClick={() => setTemplateFilter('all')}>All</button>
              {TEMPLATE_CATEGORIES.map((c) => (
                <button key={c.id} className={`design-dash-tag-btn${templateFilter === c.id ? ' active' : ''}`} onClick={() => setTemplateFilter(c.id)}>{c.label}</button>
              ))}
            </div>
            <div className="design-dash-template-grid">
              {filteredTemplates.map((t) => (
                <div key={t.id} className="design-dash-template-item" onClick={() => handleTemplateSelect(t)}>
                  <div className="design-dash-template-item-name">{t.name}</div>
                  <div className="design-dash-template-item-desc">{t.description}</div>
                </div>
              ))}
            </div>
          </div>
        )}

        <div className="design-dash-creator-footer">
          <span className="design-dash-footer-note">Designs are saved as conversations</span>
        </div>
      </aside>

      {/* Right: Gallery */}
      <main className="design-dash-gallery">
        <div className="design-dash-gallery-header">
          <div className="design-dash-tabs">
            <button className={`design-dash-tab${tab === 'recent' ? ' active' : ''}`} onClick={() => setTab('recent')}>Recent</button>
            <button className={`design-dash-tab${tab === 'examples' ? ' active' : ''}`} onClick={() => setTab('examples')}>Examples</button>
            <button className={`design-dash-tab${tab === 'design-systems' ? ' active' : ''}`} onClick={() => setTab('design-systems')}>Design systems</button>
          </div>
          {tab === 'recent' && (
            <input
              className="design-dash-search"
              placeholder="Search..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
          )}
        </div>

        <div className="design-dash-content">
          {tab === 'recent' && (
            filteredSessions.length > 0 ? (
              <div className="design-dash-grid">
                {filteredSessions.map((s) => (
                  <ProjectCard key={s.id} session={s} onClick={() => switchSession(s.id)} />
                ))}
              </div>
            ) : (
              <div className="design-dash-empty">
                <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1" opacity="0.2">
                  <rect x="3" y="3" width="18" height="18" rx="2" /><circle cx="8.5" cy="8.5" r="1.5" /><path d="M21 15l-5-5L5 21" />
                </svg>
                <p>No design projects yet</p>
                <p className="design-dash-empty-sub">Create a new prototype to get started</p>
              </div>
            )
          )}

          {tab === 'examples' && (
            <div className="design-dash-examples">
              {EXAMPLE_PROMPTS.map((ex) => (
                <ExampleCard key={ex.id} example={ex} onUse={() => handleUsePrompt(ex.prompt)} />
              ))}
            </div>
          )}

          {tab === 'design-systems' && (
            <div className="design-dash-ds-section">
              {designSystem && (
                <div className="design-dash-ds-active">
                  <div className="design-dash-ds-active-label">Active</div>
                  <div className="design-dash-ds-card">
                    <div className="design-dash-ds-card-header">
                      <div className="design-dash-ds-icon" style={{ background: designSystem.colors?.primary || 'var(--accent)' }} />
                      <div>
                        <div className="design-dash-ds-name">{designSystem.brandName || 'Design System'}</div>
                      </div>
                      <button className="design-dash-ds-clear" onClick={() => useDesignStore.getState().setDesignSystem(null)} title="Remove">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                      </button>
                    </div>
                    <div className="design-dash-ds-colors">
                      {Object.entries(designSystem.colors).slice(0, 8).map(([name, val]) => (
                        <div key={name} className="design-dash-ds-swatch" title={`${name}: ${val}`} style={{ background: val }} />
                      ))}
                    </div>
                    <div className="design-dash-ds-fonts">
                      <span>{designSystem.fonts.heading}</span>
                      {designSystem.fonts.body !== designSystem.fonts.heading && <span>{designSystem.fonts.body}</span>}
                    </div>
                  </div>
                </div>
              )}
              <h3>Presets</h3>
              <p className="design-dash-ds-desc">Select a design system to apply to all new designs.</p>
              <div className="design-dash-ds-grid">
                {PRESET_DESIGN_SYSTEMS.map((ds) => {
                  const isActive = designSystem?.brandName === ds.brandName;
                  return (
                    <div
                      key={ds.id}
                      className={`design-dash-ds-card${isActive ? ' active' : ''}`}
                      onClick={() => {
                        if (isActive) {
                          useDesignStore.getState().setDesignSystem(null);
                        } else {
                          const { id: _, description: __, ...config } = ds;
                          useDesignStore.getState().setDesignSystem(config);
                        }
                      }}
                    >
                      <div className="design-dash-ds-card-header">
                        <div className="design-dash-ds-icon" style={{ background: ds.colors.primary }} />
                        <div>
                          <div className="design-dash-ds-name">{ds.brandName}</div>
                          <div className="design-dash-ds-card-desc">{ds.description}</div>
                        </div>
                      </div>
                      <div className="design-dash-ds-colors">
                        {Object.entries(ds.colors).slice(0, 6).map(([name, val]) => (
                          <div key={name} className="design-dash-ds-swatch" title={`${name}: ${val}`} style={{ background: val }} />
                        ))}
                      </div>
                      <div className="design-dash-ds-fonts">
                        <span>{ds.fonts.heading}</span>
                        {ds.fonts.body !== ds.fonts.heading && <span>{ds.fonts.body}</span>}
                      </div>
                      {isActive && <div className="design-dash-ds-active-badge">Active</div>}
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
