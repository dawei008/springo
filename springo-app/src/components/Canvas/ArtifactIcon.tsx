/**
 * Named icon registry for artifacts. Replaces emoji-based icons so the system
 * prompt's NO-EMOJIS rule stays consistent.
 *
 * Usage:
 *   <ArtifactIcon name="dashboard" size={14} />
 *
 * Unknown names fall back to the generic "box" icon.
 */

import { memo } from 'react';

export type ArtifactIconName =
  | 'app'
  | 'component'
  | 'document'
  | 'template'
  | 'dashboard'
  | 'chart'
  | 'todo'
  | 'web'
  | 'form'
  | 'counter'
  | 'mobile'
  | 'calendar'
  | 'chat'
  | 'image'
  | 'code'
  | 'box';

type IconRenderer = (size: number) => React.ReactNode;

const common = {
  fill: 'none' as const,
  stroke: 'currentColor',
  strokeWidth: 1.8,
  strokeLinecap: 'round' as const,
  strokeLinejoin: 'round' as const,
};

const ICONS: Record<ArtifactIconName, IconRenderer> = {
  box: (s) => (
    <svg width={s} height={s} viewBox="0 0 24 24" {...common}>
      <path d="M21 8v13H3V8" />
      <path d="M1 3h22v5H1z" />
      <path d="M10 12h4" />
    </svg>
  ),
  app: (s) => (
    <svg width={s} height={s} viewBox="0 0 24 24" {...common}>
      <rect x="3" y="3" width="7" height="7" rx="1" />
      <rect x="14" y="3" width="7" height="7" rx="1" />
      <rect x="3" y="14" width="7" height="7" rx="1" />
      <rect x="14" y="14" width="7" height="7" rx="1" />
    </svg>
  ),
  component: (s) => (
    <svg width={s} height={s} viewBox="0 0 24 24" {...common}>
      <path d="M12 3l8 4.5v9L12 21l-8-4.5v-9L12 3z" />
      <path d="M12 12l8-4.5" />
      <path d="M12 12v9" />
      <path d="M12 12L4 7.5" />
    </svg>
  ),
  document: (s) => (
    <svg width={s} height={s} viewBox="0 0 24 24" {...common}>
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <path d="M14 2v6h6" />
      <path d="M8 13h8M8 17h5" />
    </svg>
  ),
  template: (s) => (
    <svg width={s} height={s} viewBox="0 0 24 24" {...common}>
      <rect x="3" y="3" width="18" height="18" rx="2" />
      <path d="M3 9h18" />
      <path d="M9 21V9" />
    </svg>
  ),
  dashboard: (s) => (
    <svg width={s} height={s} viewBox="0 0 24 24" {...common}>
      <rect x="3" y="3" width="8" height="10" rx="1" />
      <rect x="13" y="3" width="8" height="6" rx="1" />
      <rect x="13" y="11" width="8" height="10" rx="1" />
      <rect x="3" y="15" width="8" height="6" rx="1" />
    </svg>
  ),
  chart: (s) => (
    <svg width={s} height={s} viewBox="0 0 24 24" {...common}>
      <path d="M3 3v18h18" />
      <path d="M7 15l4-4 4 4 5-6" />
    </svg>
  ),
  todo: (s) => (
    <svg width={s} height={s} viewBox="0 0 24 24" {...common}>
      <rect x="3" y="4" width="18" height="17" rx="2" />
      <path d="M9 10l2 2 4-4" />
      <path d="M9 16h6" />
    </svg>
  ),
  web: (s) => (
    <svg width={s} height={s} viewBox="0 0 24 24" {...common}>
      <circle cx="12" cy="12" r="9" />
      <path d="M3 12h18" />
      <path d="M12 3c2.5 3 3.7 6 3.7 9S14.5 21 12 21s-3.7-3-3.7-9S9.5 3 12 3z" />
    </svg>
  ),
  form: (s) => (
    <svg width={s} height={s} viewBox="0 0 24 24" {...common}>
      <rect x="3" y="5" width="18" height="14" rx="2" />
      <path d="M7 10h10M7 14h6" />
    </svg>
  ),
  counter: (s) => (
    <svg width={s} height={s} viewBox="0 0 24 24" {...common}>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v5l3 2" />
    </svg>
  ),
  mobile: (s) => (
    <svg width={s} height={s} viewBox="0 0 24 24" {...common}>
      <rect x="6" y="2" width="12" height="20" rx="2" />
      <path d="M11 18h2" />
    </svg>
  ),
  calendar: (s) => (
    <svg width={s} height={s} viewBox="0 0 24 24" {...common}>
      <rect x="3" y="5" width="18" height="16" rx="2" />
      <path d="M3 10h18M8 3v4M16 3v4" />
    </svg>
  ),
  chat: (s) => (
    <svg width={s} height={s} viewBox="0 0 24 24" {...common}>
      <path d="M21 12a8 8 0 0 1-11.5 7.2L4 21l1.8-5.5A8 8 0 1 1 21 12z" />
    </svg>
  ),
  image: (s) => (
    <svg width={s} height={s} viewBox="0 0 24 24" {...common}>
      <rect x="3" y="3" width="18" height="18" rx="2" />
      <circle cx="9" cy="9" r="1.5" />
      <path d="M21 15l-5-5L5 21" />
    </svg>
  ),
  code: (s) => (
    <svg width={s} height={s} viewBox="0 0 24 24" {...common}>
      <path d="M8 6l-5 6 5 6" />
      <path d="M16 6l5 6-5 6" />
      <path d="M14 4l-4 16" />
    </svg>
  ),
};

/** All icon names the UI and AI may reference. */
export const ARTIFACT_ICON_NAMES: ArtifactIconName[] = [
  'app', 'component', 'document', 'template',
  'dashboard', 'chart', 'todo', 'web', 'form', 'counter',
  'mobile', 'calendar', 'chat', 'image', 'code', 'box',
];

export function resolveIconName(name: string | undefined | null, fallbackByType?: string): ArtifactIconName {
  if (name && name in ICONS) return name as ArtifactIconName;
  if (fallbackByType && fallbackByType in ICONS) return fallbackByType as ArtifactIconName;
  return 'box';
}

interface Props {
  name: string | undefined | null;
  /** Used when `name` isn't recognized — typically the artifact's type. */
  fallback?: string;
  size?: number;
}

export const ArtifactIcon = memo(function ArtifactIcon({ name, fallback, size = 14 }: Props) {
  const resolved = resolveIconName(name, fallback);
  return <span className="artifact-icon" aria-hidden="true">{ICONS[resolved](size)}</span>;
});
