/**
 * Dev-time debugging hook.
 *
 * Mounts `window.__springoDev` in dev builds (and in Electron dev mode via
 * VITE_EXPOSE_DEV_HOOK=1) so interactive debugging + automated scripts can
 * reach stores, iframe innards, and common test affordances without going
 * through the Chrome DevTools Protocol.
 *
 * Usage from a DevTools console or a WebSocket-driven test:
 *
 *   window.__springoDev.stores.artifacts.getState()
 *   window.__springoDev.iframe.click('+')
 *   window.__springoDev.iframe.readState()
 *   await window.__springoDev.createFromTemplate('tpl-counter')
 *
 * This module has zero cost in production builds — the conditional at the
 * bottom bails out before touching window.
 */

import { useArtifactStore } from '@/stores/artifactStore';
import { useChatStore } from '@/stores/chatStore';
import { usePlanStore } from '@/stores/planStore';
import { useSessionStore } from '@/stores/sessionStore';
import { useSettingsStore } from '@/stores/settingsStore';
import { useSkillProposalsStore } from '@/stores/skillProposalsStore';
import { useUIStore } from '@/stores/uiStore';
import {
  useUnifiedArtifactStore,
  type UnifiedArtifactState,
} from '@/stores/unifiedArtifactStore';
import { ARTIFACT_TEMPLATES } from '@/data/artifactTemplates';

interface DevHook {
  stores: {
    artifacts: typeof useUnifiedArtifactStore;
    legacyArtifacts: typeof useArtifactStore;
    chat: typeof useChatStore;
    plan: typeof usePlanStore;
    session: typeof useSessionStore;
    settings: typeof useSettingsStore;
    skillProposals: typeof useSkillProposalsStore;
    ui: typeof useUIStore;
  };

  /** Operate on the active artifact's iframe without going through CDP. */
  iframe: {
    /** Return the active artifact iframe element, or null. */
    el(): HTMLIFrameElement | null;
    /** Return the live document inside the iframe, or null. */
    doc(): Document | null;
    /**
     * Click the first button whose trimmed text matches `label`.
     *
     * Caveat: React 18's concurrent scheduler (loaded via UMD inside the
     * iframe) frequently fails to commit the resulting state update when
     * the click is synthesized from outside. Use this for sanity checks;
     * if you need guaranteed round-trips, ask the model to emit a
     * `<springo-action>` instead, or click the button manually.
     */
    click(label: string): boolean;
    /** `querySelector` inside the iframe document. */
    $(selector: string): Element | null;
    /** Read whatever state the artifact has reported via `window.springo.setState`. */
    readState(): Record<string, unknown> | null;
  };

  /** Create a Canvas artifact from a built-in template by id (e.g. `tpl-counter`). */
  createFromTemplate(templateId: string): string | null;

  /** Force the skill-proposals banner poller to fetch now. */
  refreshProposals(): Promise<void>;

  /** List every tool the hook exposes — handy for discovery in a fresh console. */
  help(): string[];
}

function buildDevHook(): DevHook {
  const activeArtifact = (): UnifiedArtifactState['artifacts'][string] | null => {
    const s = useUnifiedArtifactStore.getState();
    return s.activeArtifactId ? s.artifacts[s.activeArtifactId] ?? null : null;
  };

  const iframeEl = (): HTMLIFrameElement | null =>
    document.querySelector<HTMLIFrameElement>('.artifact-iframe');

  return {
    stores: {
      artifacts: useUnifiedArtifactStore,
      legacyArtifacts: useArtifactStore,
      chat: useChatStore,
      plan: usePlanStore,
      session: useSessionStore,
      settings: useSettingsStore,
      skillProposals: useSkillProposalsStore,
      ui: useUIStore,
    },

    iframe: {
      el: iframeEl,
      doc: () => iframeEl()?.contentDocument ?? null,
      click: (label: string): boolean => {
        const iframe = iframeEl();
        const view = iframe?.contentWindow as (Window & typeof globalThis) | null | undefined;
        if (!view) return false;
        // Execute inside the iframe's own realm — otherwise the click is
        // queued against the host frame's scheduler and React's commit
        // never runs inside the iframe.
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const run = ((view as any).eval as (src: string) => unknown);
        try {
          const ok = run(
            '(function(label){' +
              'var btn=Array.prototype.find.call(document.querySelectorAll("button"),function(b){return (b.textContent||"").trim()===label;});' +
              'if(!btn) return false;' +
              'btn.dispatchEvent(new MouseEvent("mousedown",{bubbles:true,cancelable:true,view:window}));' +
              'btn.dispatchEvent(new MouseEvent("mouseup",{bubbles:true,cancelable:true,view:window}));' +
              'btn.dispatchEvent(new MouseEvent("click",{bubbles:true,cancelable:true,view:window}));' +
              'return true;' +
            '})(' + JSON.stringify(label) + ')',
          );
          return Boolean(ok);
        } catch {
          return false;
        }
      },
      $: (selector: string) => iframeEl()?.contentDocument?.querySelector(selector) ?? null,
      readState: () => {
        const art = activeArtifact();
        return art ? art.state ?? {} : null;
      },
    },

    createFromTemplate: (templateId: string): string | null => {
      const tpl = ARTIFACT_TEMPLATES.find((t) => t.id === templateId);
      if (!tpl) return null;
      return useUnifiedArtifactStore.getState().createArtifact({
        name: tpl.name,
        icon: tpl.icon,
        type: tpl.type,
        files: tpl.files.map((f) => ({ ...f })),
      });
    },

    refreshProposals: () => useSkillProposalsStore.getState().fetchPending(),

    help: () => [
      'stores.{artifacts,chat,plan,session,settings,skillProposals,ui}.getState()',
      'iframe.el() | iframe.doc() | iframe.$(sel) | iframe.click(label) | iframe.readState()',
      'createFromTemplate("tpl-counter" | "tpl-dashboard" | "tpl-todo" | "tpl-landing" | "tpl-form")',
      'refreshProposals() — force-poll skill proposals',
    ],
  };
}

declare global {
  interface Window {
    __springoDev?: DevHook;
  }
}

// Mount the hook in three scenarios:
//   1. vite dev server (import.meta.env.DEV === true)
//   2. build-time opt-in via VITE_EXPOSE_DEV_HOOK=1
//   3. runtime opt-in: localStorage.setItem('springo-dev-hook', '1')
// The packaged app ships a production build, so (3) is the way to enable
// the hook in a normal Electron window without a custom build.
function shouldMount(): boolean {
  if (import.meta.env.DEV) return true;
  if (import.meta.env.VITE_EXPOSE_DEV_HOOK === '1') return true;
  try {
    return typeof localStorage !== 'undefined' && localStorage.getItem('springo-dev-hook') === '1';
  } catch {
    return false;
  }
}

if (shouldMount() && typeof window !== 'undefined') {
  window.__springoDev = buildDevHook();
  // eslint-disable-next-line no-console
  console.info('[springo] dev hook mounted. Try: window.__springoDev.help()');
}

export {};
