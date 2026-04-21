import { useState, type ReactNode } from 'react';
import { DESIGN_TEMPLATES, TEMPLATE_CATEGORIES, type DesignTemplate } from '@/data/designTemplates';

const CATEGORY_ICONS: Record<string, ReactNode> = {
  mobile: <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><rect x="6" y="2" width="12" height="20" rx="2" /><line x1="12" y1="18" x2="12.01" y2="18" /></svg>,
  web: <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><rect x="2" y="4" width="20" height="14" rx="2" /><line x1="2" y1="8" x2="22" y2="8" /><circle cx="5" cy="6" r="0.5" fill="currentColor" /><circle cx="7.5" cy="6" r="0.5" fill="currentColor" /><circle cx="10" cy="6" r="0.5" fill="currentColor" /></svg>,
  slides: <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><rect x="2" y="3" width="20" height="14" rx="2" /><path d="M8 21h8M12 17v4" /></svg>,
  component: <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><rect x="3" y="3" width="7" height="7" rx="1" /><rect x="14" y="3" width="7" height="7" rx="1" /><rect x="3" y="14" width="7" height="7" rx="1" /><rect x="14" y="14" width="7" height="7" rx="1" /></svg>,
};

export default function DesignTemplateLibrary({ onSelect }: { onSelect: (template: DesignTemplate) => void }) {
  const [activeCategory, setActiveCategory] = useState<string>('all');

  const filtered = activeCategory === 'all'
    ? DESIGN_TEMPLATES
    : DESIGN_TEMPLATES.filter(t => t.category === activeCategory);

  return (
    <div className="design-template-library">
      <div className="design-template-tabs">
        <button
          className={`design-template-tab${activeCategory === 'all' ? ' active' : ''}`}
          onClick={() => setActiveCategory('all')}
        >
          All
        </button>
        {TEMPLATE_CATEGORIES.map(cat => (
          <button
            key={cat.id}
            className={`design-template-tab${activeCategory === cat.id ? ' active' : ''}`}
            onClick={() => setActiveCategory(cat.id)}
          >
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d={cat.icon} />
            </svg>
            {cat.label}
          </button>
        ))}
      </div>
      <div className="design-template-grid">
        {filtered.map(t => (
          <button
            key={t.id}
            className="design-template-card"
            onClick={() => onSelect(t)}
            title={t.description}
          >
            <div className="design-template-card-icon">
              {CATEGORY_ICONS[t.category]}
            </div>
            <span className="design-template-card-name">{t.name}</span>
            <span className="design-template-card-desc">{t.description}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
