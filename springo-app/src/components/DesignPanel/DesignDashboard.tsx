import { useState, useMemo, useCallback, useRef } from 'react';
import { useSessionStore } from '@/stores/sessionStore';
import { useSettingsStore } from '@/stores/settingsStore';
import { useChatStore } from '@/stores/chatStore';
import { useDesignStore } from '@/stores/designStore';
import { useUIStore } from '@/stores/uiStore';
import { DESIGN_TEMPLATES, TEMPLATE_CATEGORIES, type DesignTemplate } from '@/data/designTemplates';
import type { DesignSystemConfig, DesignSystemSource } from '@/types';

type DashboardTab = 'recent' | 'examples' | 'design-systems';
type CreatorType = 'prototype' | 'slides' | 'template';

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
    const ds = useDesignStore.getState().designSystem;

    // Rename current session if it's still "New Chat" / default
    const ss = useSessionStore.getState();
    const cur = ss.sessions.find(s => s.id === ss.currentSessionId);
    if (cur && (!cur.title || ['New Chat', 'New Design'].includes(cur.title))) {
      ss.renameSession(cur.id, title);
    }

    const fidelityHint = fidelity === 'wireframe'
      ? 'Create a low-fidelity wireframe with grayscale colors and simple shapes.'
      : 'Create a high-fidelity design with polished visuals and production-ready styling.';

    const dsHint = ds?.brandName ? ` Use ${ds.brandName} design system.` : '';

    const prompt = `${fidelityHint}${dsHint}\n\nDesign: ${title}`;
    useUIStore.getState().setPendingPrompt(prompt);
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
            <DesignSystemTab designSystem={designSystem} />
          )}
        </div>
      </main>
    </div>
  );
}

// ─── Design System Tab (Claude.ai Organization Settings style) ───

type DSFilter = 'all' | 'published' | 'drafts';
type DSView = 'list' | 'create' | 'detail';

interface UploadedFile {
  name: string;
  type: string;
  data: string;
}

function DesignSystemTab({ designSystem }: { designSystem: DesignSystemConfig | null }) {
  const designSystems = useDesignStore((s) => s.designSystems);
  const addDesignSystem = useDesignStore((s) => s.addDesignSystem);
  const removeDesignSystem = useDesignStore((s) => s.removeDesignSystem);
  const updateDesignSystem = useDesignStore((s) => s.updateDesignSystem);
  const setDefaultDesignSystem = useDesignStore((s) => s.setDefaultDesignSystem);

  const [view, setView] = useState<DSView>('list');
  const [filter, setFilter] = useState<DSFilter>('all');
  const [search, setSearch] = useState('');
  const [openId, setOpenId] = useState<string | null>(null);
  const [editingDS, setEditingDS] = useState<DesignSystemConfig | undefined>(undefined);

  const filtered = useMemo(() => {
    let list = designSystems;
    if (filter === 'published') list = list.filter((d) => d.published);
    if (filter === 'drafts') list = list.filter((d) => !d.published);
    if (search) {
      const q = search.toLowerCase();
      list = list.filter((d) => (d.brandName || '').toLowerCase().includes(q));
    }
    return list;
  }, [designSystems, filter, search]);

  if (view === 'create') {
    return <DSCreateForm onBack={() => { setView('list'); setEditingDS(undefined); }} onCreated={() => { setView('list'); setEditingDS(undefined); setOpenId(null); }} editDS={editingDS} />;
  }

  const openDS = openId ? designSystems.find((d) => d.id === openId) : null;
  if (openDS) {
    return <DesignSystemDetail ds={openDS} onBack={() => setOpenId(null)} onEdit={() => { setEditingDS(openDS); setView('create'); }} />;
  }

  return (
    <div className="ds-settings">
      <div className="ds-settings-section-label">DESIGN SYSTEMS</div>

      <div className="ds-settings-toolbar">
        <input
          className="ds-settings-search"
          placeholder="Search design systems"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <div className="ds-settings-filter-tabs">
          {(['all', 'published', 'drafts'] as DSFilter[]).map((f) => (
            <button key={f} className={`ds-settings-filter-tab${filter === f ? ' active' : ''}`} onClick={() => setFilter(f)}>
              {f.charAt(0).toUpperCase() + f.slice(1)}
            </button>
          ))}
        </div>
      </div>

      <div className="ds-settings-list">
        <div className="ds-settings-row ds-settings-create-row">
          <div className="ds-settings-row-info">
            <div className="ds-settings-row-title">Create new design system</div>
            <div className="ds-settings-row-sub">Teach Springo your brand and product</div>
          </div>
          <button className="ds-settings-create-btn" onClick={() => setView('create')}>Create</button>
        </div>

        {filtered.map((ds) => (
          <div key={ds.id} className="ds-settings-row">
            <div className="ds-settings-row-info">
              <div className="ds-settings-row-title-line">
                <span className="ds-settings-row-title">{ds.brandName || 'Design System'}</span>
                {ds.isDefault && <span className="ds-settings-default-badge">DEFAULT</span>}
              </div>
              <div className="ds-settings-row-sub">
                {ds.author || 'you'} · {ds.createdAt ? formatRelativeTime(ds.createdAt) : ''}
              </div>
            </div>
            <div className="ds-settings-row-actions">
              <label className="ds-settings-row-publish">
                Published
                <input
                  type="checkbox"
                  className="ds-settings-toggle"
                  checked={!!ds.published}
                  onChange={() => updateDesignSystem(ds.id!, { published: !ds.published })}
                />
                <span className="ds-settings-toggle-track" />
              </label>
              <button className="ds-settings-open-btn" onClick={() => setOpenId(ds.id!)}>
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>
                  <polyline points="15 3 21 3 21 9"/>
                  <line x1="10" y1="14" x2="21" y2="3"/>
                </svg>
                Open
              </button>
            </div>
          </div>
        ))}

        {filtered.length === 0 && designSystems.length > 0 && (
          <div className="ds-settings-empty-filter">No design systems match your filter.</div>
        )}
      </div>

      <div className="ds-settings-section-label" style={{ marginTop: 32 }}>TEMPLATES</div>
      <div className="ds-settings-templates-empty">
        No templates yet. Create one from any project via the Share menu → File type.
      </div>

      <div className="ds-settings-footer">Only you can view these settings.</div>
    </div>
  );
}

// ─── Create / Edit Design System Form (Claude.ai style) ───

function DSCreateForm({ onBack, onCreated, editDS }: { onBack: () => void; onCreated: () => void; editDS?: DesignSystemConfig }) {
  const addDesignSystem = useDesignStore((s) => s.addDesignSystem);
  const updateDesignSystem = useDesignStore((s) => s.updateDesignSystem);
  const [companyBlurb, setCompanyBlurb] = useState(editDS?.source?.companyBlurb || '');
  const [githubUrl, setGithubUrl] = useState('');
  const [githubLinks, setGithubLinks] = useState<string[]>(editDS?.source?.githubLinks || []);
  const [codeFiles, setCodeFiles] = useState<UploadedFile[]>([]);
  const [assetFiles, setAssetFiles] = useState<UploadedFile[]>([]);
  const [notes, setNotes] = useState(editDS?.source?.notes || '');
  const [generating, setGenerating] = useState(false);

  const codeInputRef = useRef<HTMLInputElement>(null);
  const assetInputRef = useRef<HTMLInputElement>(null);

  const githubInputRef = useRef<HTMLInputElement>(null);

  const addGithubLink = () => {
    const url = (githubInputRef.current?.value || githubUrl).trim();
    if (url && !githubLinks.includes(url)) {
      setGithubLinks((prev) => [...prev, url]);
      setGithubUrl('');
      if (githubInputRef.current) githubInputRef.current.value = '';
    }
  };

  const readFiles = useCallback(async (files: FileList | File[]): Promise<UploadedFile[]> => {
    const results: UploadedFile[] = [];
    for (const file of Array.from(files)) {
      if (file.type.startsWith('image/')) {
        const data = await new Promise<string>((resolve) => {
          const reader = new FileReader();
          reader.onload = () => resolve(reader.result as string);
          reader.readAsDataURL(file);
        });
        results.push({ name: file.name, type: file.type, data });
      } else {
        const text = await file.text();
        results.push({ name: file.name, type: file.type, data: text.slice(0, 3000) });
      }
    }
    return results;
  }, []);

  const handleCodeDrop = useCallback(async (e: React.DragEvent) => {
    e.preventDefault();
    if (e.dataTransfer.files.length > 0) {
      const files = await readFiles(e.dataTransfer.files);
      setCodeFiles((prev) => [...prev, ...files]);
    }
  }, [readFiles]);

  const handleAssetDrop = useCallback(async (e: React.DragEvent) => {
    e.preventDefault();
    if (e.dataTransfer.files.length > 0) {
      const files = await readFiles(e.dataTransfer.files);
      setAssetFiles((prev) => [...prev, ...files]);
    }
  }, [readFiles]);

  const handleGenerate = useCallback(async () => {
    if (!companyBlurb.trim()) return;
    setGenerating(true);
    try {
      const parts: string[] = [];
      parts.push(`Company: ${companyBlurb}`);
      if (githubLinks.length > 0) parts.push(`GitHub repos:\n${githubLinks.join('\n')}`);
      if (codeFiles.length > 0) {
        for (const f of codeFiles) {
          parts.push(`[Code file: ${f.name}]\n${f.data}`);
        }
      }
      if (assetFiles.length > 0) {
        for (const f of assetFiles) {
          if (f.type.startsWith('image/')) {
            parts.push(`[Asset image: ${f.name}] (${f.data.slice(0, 80)}...)`);
          } else {
            parts.push(`[Asset: ${f.name}]\n${f.data}`);
          }
        }
      }
      if (notes.trim()) parts.push(`Additional notes: ${notes}`);

      const prompt = `You are a design system expert. Based on the following company info and brand assets, create a comprehensive design system. Return ONLY a JSON object with this exact structure (no markdown, no explanation):
{"brandName":"Brand Name","colors":{"primary":"#hex","secondary":"#hex","accent":"#hex","background":"#hex","surface":"#hex","text":"#hex"},"fonts":{"heading":"Font Name","body":"Font Name"},"components":["Component1","Component2"]}

${parts.join('\n\n')}`;

      const settings = useSettingsStore.getState().settings;
      const res = await fetch('http://127.0.0.1:8081/v1/messages', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          model: settings.model || 'anthropic.claude-sonnet-4-20250514-v1:0',
          messages: [{ role: 'user', content: prompt }],
          max_tokens: 1024,
          temperature: 0,
        }),
      });
      if (res.ok) {
        const data = await res.json();
        const text = data.content?.[0]?.text || '';
        const jsonMatch = text.match(/\{[\s\S]*\}/);
        if (jsonMatch) {
          const config: DesignSystemConfig = JSON.parse(jsonMatch[0]);
          const sourceData: DesignSystemSource = {
            companyBlurb,
            githubLinks,
            notes,
            codeFileNames: [
              ...(editDS?.source?.codeFileNames || []),
              ...codeFiles.map(f => f.name),
            ],
            assetFileNames: [
              ...(editDS?.source?.assetFileNames || []),
              ...assetFiles.map(f => f.name),
            ],
          };
          if (editDS?.id) {
            updateDesignSystem(editDS.id, { ...config, source: sourceData, updatedAt: Date.now() });
          } else {
            addDesignSystem({ ...config, published: true, author: 'you', source: sourceData });
          }
          onCreated();
        }
      }
    } catch (e) {
      console.error('DS generation failed:', e);
    } finally {
      setGenerating(false);
    }
  }, [companyBlurb, githubLinks, codeFiles, assetFiles, notes, addDesignSystem, onCreated]);

  return (
    <div className="ds-create">
      <div className="ds-create-header">
        <svg width="28" height="28" viewBox="0 0 24 24" fill="none" opacity="0.6">
          <circle cx="12" cy="12" r="4" fill="#c2410c" />
          {[0,30,60,90,120,150,180,210,240,270,300,330].map((deg) => (
            <line key={deg} x1="12" y1="3" x2="12" y2="5" stroke="#c2410c" strokeWidth="1.5" strokeLinecap="round"
              transform={`rotate(${deg} 12 12)`} />
          ))}
        </svg>
        <h2 className="ds-create-title">{editDS ? 'Edit your design system' : 'Set up your design system'}</h2>
        <p className="ds-create-subtitle">{editDS ? 'Update your company info and regenerate the design system.' : 'Tell us about your company and attach any design resources you have.'}</p>
      </div>

      {/* Company name and blurb */}
      <div className="ds-create-field">
        <label className="ds-create-label">
          <strong>Company name and blurb</strong> (or name of design system)
        </label>
        <textarea
          className="ds-create-textarea"
          placeholder="e.g. Springo: AI-powered design assistant with warm, friendly interface for creative professionals"
          value={companyBlurb}
          onChange={(e) => setCompanyBlurb(e.target.value)}
          rows={4}
        />
      </div>

      {/* Examples section */}
      <div className="ds-create-field">
        <label className="ds-create-label">
          <strong>Provide examples of your design system and products</strong> (all optional)
        </label>
        <p className="ds-create-hint">What works best: code and designs for your design system and your code products.</p>

        <div className="ds-create-examples">
          {/* GitHub link */}
          <div className="ds-create-example-row">
            <div className="ds-create-example-label"><strong>Link code on GitHub</strong></div>
            <div className="ds-create-example-input-group">
              <input
                ref={githubInputRef}
                className="ds-create-example-input"
                placeholder="https://github.com/owner/repo"
                value={githubUrl}
                onChange={(e) => setGithubUrl(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') addGithubLink(); }}
              />
              <button className="ds-create-example-add-btn" onClick={addGithubLink}>Add</button>
            </div>
            {githubLinks.length > 0 && (
              <div className="ds-create-linked-items">
                {githubLinks.map((url, i) => (
                  <div key={i} className="ds-create-linked-item">
                    <span>{url}</span>
                    <button onClick={() => setGithubLinks((prev) => prev.filter((_, j) => j !== i))}>×</button>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Local code */}
          <div className="ds-create-example-row">
            <div className="ds-create-example-label"><strong>Link code from your computer</strong></div>
            <div
              className="ds-create-dropzone"
              onDragOver={(e) => e.preventDefault()}
              onDrop={handleCodeDrop}
              onClick={() => codeInputRef.current?.click()}
            >
              Drag a folder here or <strong>browse</strong>
            </div>
            <input
              ref={codeInputRef}
              type="file"
              multiple
              accept=".css,.json,.html,.tsx,.jsx,.ts,.js,.svg,.scss,.less"
              style={{ display: 'none' }}
              onChange={async (e) => {
                if (e.target.files) {
                  const files = await readFiles(e.target.files);
                  setCodeFiles((prev) => [...prev, ...files]);
                }
                e.target.value = '';
              }}
            />
            <p className="ds-create-example-note">
              This doesn't upload the whole codebase; Springo will copy selected files. For large codebases, we recommend attaching a frontend-focused subfolder.
            </p>
            {codeFiles.length > 0 && (
              <div className="ds-create-linked-items">
                {codeFiles.map((f, i) => (
                  <div key={i} className="ds-create-linked-item">
                    <span>{f.name}</span>
                    <button onClick={() => setCodeFiles((prev) => prev.filter((_, j) => j !== i))}>×</button>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Assets */}
          <div className="ds-create-example-row">
            <div className="ds-create-example-label"><strong>Add fonts, logos and assets</strong></div>
            <div
              className="ds-create-dropzone"
              onDragOver={(e) => e.preventDefault()}
              onDrop={handleAssetDrop}
              onClick={() => assetInputRef.current?.click()}
            >
              Drag files here or <strong>browse</strong>
            </div>
            <input
              ref={assetInputRef}
              type="file"
              multiple
              accept="image/*,.svg,.woff,.woff2,.ttf,.otf,.pdf"
              style={{ display: 'none' }}
              onChange={async (e) => {
                if (e.target.files) {
                  const files = await readFiles(e.target.files);
                  setAssetFiles((prev) => [...prev, ...files]);
                }
                e.target.value = '';
              }}
            />
            {assetFiles.length > 0 && (
              <div className="ds-create-linked-items">
                {assetFiles.map((f, i) => (
                  <div key={i} className="ds-create-linked-item">
                    <span>{f.name}</span>
                    <button onClick={() => setAssetFiles((prev) => prev.filter((_, j) => j !== i))}>×</button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Notes */}
      <div className="ds-create-field">
        <label className="ds-create-label"><strong>Any other notes?</strong></label>
        <textarea
          className="ds-create-textarea"
          placeholder="e.g. We use a warm, earthy color palette with rounded corners. Our brand voice is playful but professional."
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          rows={3}
        />
      </div>

      {/* Actions */}
      <div className="ds-create-actions">
        <button className="ds-create-cancel" onClick={onBack}>Cancel</button>
        <button
          className="ds-create-submit"
          onClick={handleGenerate}
          disabled={generating || !companyBlurb.trim()}
        >
          {generating ? 'Generating...' : editDS ? 'Regenerate design system' : 'Create design system'}
        </button>
      </div>
    </div>
  );
}

// ─── Design System Detail View ───

function DesignSystemDetail({ ds, onBack, onEdit }: { ds: DesignSystemConfig; onBack: () => void; onEdit: () => void }) {
  const updateDesignSystem = useDesignStore((s) => s.updateDesignSystem);
  const removeDesignSystem = useDesignStore((s) => s.removeDesignSystem);
  const setDefaultDesignSystem = useDesignStore((s) => s.setDefaultDesignSystem);
  const [editName, setEditName] = useState(false);
  const [name, setName] = useState(ds.brandName || '');
  const src = ds.source;

  return (
    <div className="ds-detail">
      <button className="ds-detail-back" onClick={onBack}>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="15 18 9 12 15 6"/></svg>
        Back to settings
      </button>

      <div className="ds-detail-header">
        <div className="ds-detail-icon" style={{ background: ds.colors?.primary || 'var(--accent)' }} />
        <div>
          {editName ? (
            <input
              className="ds-detail-name-input"
              value={name}
              onChange={(e) => setName(e.target.value)}
              onBlur={() => { updateDesignSystem(ds.id!, { brandName: name.trim() || ds.brandName }); setEditName(false); }}
              onKeyDown={(e) => { if (e.key === 'Enter') (e.target as HTMLInputElement).blur(); if (e.key === 'Escape') setEditName(false); }}
              autoFocus
            />
          ) : (
            <h2 className="ds-detail-name" onClick={() => setEditName(true)}>{ds.brandName || 'Design System'}</h2>
          )}
          <div className="ds-detail-badges">
            {ds.isDefault && <span className="ds-settings-default-badge">DEFAULT</span>}
            {ds.updatedAt && <span className="ds-detail-updated">Updated {formatRelativeTime(ds.updatedAt)}</span>}
          </div>
        </div>
      </div>

      {/* Source info */}
      {src && (
        <div className="ds-detail-source">
          <div className="ds-detail-section-label">Source</div>
          <div className="ds-detail-source-card">
            {src.companyBlurb && (
              <div className="ds-detail-source-row">
                <span className="ds-detail-source-key">Company</span>
                <span className="ds-detail-source-val">{src.companyBlurb}</span>
              </div>
            )}
            {src.githubLinks.length > 0 && (
              <div className="ds-detail-source-row">
                <span className="ds-detail-source-key">GitHub</span>
                <span className="ds-detail-source-val">{src.githubLinks.join(', ')}</span>
              </div>
            )}
            {src.codeFileNames.length > 0 && (
              <div className="ds-detail-source-row">
                <span className="ds-detail-source-key">Code files</span>
                <span className="ds-detail-source-val">{src.codeFileNames.join(', ')}</span>
              </div>
            )}
            {src.assetFileNames.length > 0 && (
              <div className="ds-detail-source-row">
                <span className="ds-detail-source-key">Assets</span>
                <span className="ds-detail-source-val">{src.assetFileNames.join(', ')}</span>
              </div>
            )}
            {src.notes && (
              <div className="ds-detail-source-row">
                <span className="ds-detail-source-key">Notes</span>
                <span className="ds-detail-source-val">{src.notes}</span>
              </div>
            )}
          </div>
        </div>
      )}

      <div className="ds-detail-section">
        <div className="ds-detail-section-label">Colors</div>
        <div className="ds-detail-colors">
          {ds.colors && Object.entries(ds.colors).map(([k, v]) => (
            <div key={k} className="ds-detail-swatch">
              <div className="ds-detail-swatch-color" style={{ background: v }} />
              <span className="ds-detail-swatch-name">{k}</span>
              <span className="ds-detail-swatch-value">{v}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="ds-detail-section">
        <div className="ds-detail-section-label">Typography</div>
        <div className="ds-detail-typo">
          <div><strong>Heading:</strong> {ds.fonts?.heading}</div>
          <div><strong>Body:</strong> {ds.fonts?.body}</div>
        </div>
      </div>

      {ds.components && ds.components.length > 0 && (
        <div className="ds-detail-section">
          <div className="ds-detail-section-label">Components</div>
          <div className="ds-detail-components">
            {ds.components.map((c) => <span key={c} className="ds-detail-component">{c}</span>)}
          </div>
        </div>
      )}

      <div className="ds-detail-actions">
        <button className="ds-detail-action-btn ds-detail-edit-btn" onClick={onEdit}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
            <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
          </svg>
          Edit &amp; Regenerate
        </button>
        {!ds.isDefault && (
          <button className="ds-detail-action-btn" onClick={() => { setDefaultDesignSystem(ds.id!); }}>
            Set as default
          </button>
        )}
        <button className="ds-detail-action-btn ds-detail-delete" onClick={() => { removeDesignSystem(ds.id!); onBack(); }}>
          Delete
        </button>
      </div>
    </div>
  );
}
