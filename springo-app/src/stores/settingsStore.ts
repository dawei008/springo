import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { Settings, ModelInfo } from '@/types';

const BASE_URL = 'http://127.0.0.1:8081';

/** Removed model -> replacement model migration map */
const REMOVED_MODEL_MIGRATION: Record<string, string> = {
  'claude-3-haiku-20240307': 'claude-haiku-4-5-20251001',
  'claude-3-sonnet-20240229': 'claude-sonnet-4-5-20250929',
  'claude-3-opus-20240229': 'claude-opus-4-6',
  'claude-3-5-haiku-20241022': 'claude-haiku-4-5-20251001',
  'claude-3-5-sonnet-20241022': 'claude-sonnet-4-5-20250929',
  'claude-3-7-sonnet-20250219': 'claude-sonnet-4-5-20250929',
  'claude-sonnet-4-20250514': 'claude-sonnet-4-6',
  'claude-sonnet-4-5-20250929': 'claude-sonnet-4-6',
  'claude-opus-4-20250514': 'claude-opus-4-6',
  'claude-opus-4-5-20251101': 'claude-opus-4-6',
  'claude-opus-4-1-20250805': 'claude-opus-4-6',
  'deepseek-r1': 'deepseek-v3.2',
  'deepseek-v3.1': 'deepseek-v3.2',
  'minimax-m2': 'minimax-m2.5',
  'minimax-m2.1': 'minimax-m2.5',
  'kimi-k2-thinking': 'kimi-k2.5',
  'qwen3-235b': 'qwen3-coder-480b',
  'qwen3-32b': 'qwen3-coder-480b',
  'qwen3-vl-235b': 'qwen3-coder-480b',
  'qwen3-coder-30b': 'qwen3-coder-480b',
  'glm-4.7': 'glm-5',
  'glm-4.7-flash': 'glm-5',
};

interface SettingsState {
  settings: Settings;
  models: ModelInfo[];
  modelsByProvider: Record<string, ModelInfo[]>;
  defaultModel: string;
  defaultCompactModel: string;

  // Working directory
  workingDir: string;
  workingFolders: string[];
  defaultWorkingFolder: string;

  // Actions
  loadSettings: () => void;
  saveSettings: (partial: Partial<Settings>) => void;
  loadModels: () => Promise<void>;
  loadWorkingDir: () => Promise<void>;
  setWorkingDir: (dir: string) => void;
  migrateSettings: () => void;
  getEffectiveModel: () => string;
  getEffectiveCompactModel: () => string;
}

const DEFAULT_SETTINGS: Settings = {
  model: 'claude-opus-4-7',
  maxTokens: 16384,
  temperature: 0.7,
  compactModel: 'claude-haiku-4-5-20251001',
  thinkingEnabled: true,
  thinkingEffort: 'xhigh',
};

export const useSettingsStore = create<SettingsState>()(
  persist(
    (set, get) => ({
      settings: { ...DEFAULT_SETTINGS },
      models: [],
      modelsByProvider: {},
      defaultModel: 'claude-opus-4-7',
      defaultCompactModel: 'claude-haiku-4-5-20251001',

      workingDir: '',
      workingFolders: [],
      defaultWorkingFolder: '~/Downloads',

      loadSettings: () => {
        // Migrate on load
        get().migrateSettings();
      },

      saveSettings: (partial: Partial<Settings>) => {
        set((state) => ({
          settings: { ...state.settings, ...partial },
        }));
      },

      loadModels: async () => {
        try {
          const res = await fetch(`${BASE_URL}/v1/models`);
          const data = await res.json();

          const models = (data.data || []) as ModelInfo[];
          const modelsByProvider = (data.models || {}) as Record<string, ModelInfo[]>;
          const defaultModel = (data.default_model as string) || 'claude-opus-4-6';
          const defaultCompactModel =
            (data.default_compact_model as string) || 'claude-haiku-4-5-20251001';

          set({ models, modelsByProvider, defaultModel, defaultCompactModel });
        } catch (e) {
          console.warn('[Models] Failed to load from API:', (e as Error).message);
        }
      },

      loadWorkingDir: async () => {
        // Load default working folder from backend (primary source of truth)
        try {
          const res = await fetch(`${BASE_URL}/v1/config/default-working-folder`);
          if (res.ok) {
            const data = await res.json();
            const backendDefault = data.default_working_folder as string;
            if (backendDefault) {
              set({ defaultWorkingFolder: backendDefault });
            }
          }
        } catch (e) {
          console.warn('[Settings] Failed to load default working folder from backend:', e);
        }
        // Load working folders from Electron cache (for folder list only)
        const current = get();
        if (current.workingFolders.length > 0 || current.workingDir) {
          return;
        }
        if (window.electronAPI?.cache) {
          try {
            const raw = await window.electronAPI.cache.get('workspace');
            const cached = raw as Record<string, unknown> | null;
            if (cached) {
              set({
                workingFolders: (cached.workingFolders as string[]) || [],
                workingDir: (cached.currentWorkingDir as string) || '',
              });
            }
          } catch (e) {
            console.error('Failed to load workspace cache:', e);
          }
        }
      },

      setWorkingDir: (dir: string) => {
        set({ workingDir: dir });
        // Persist to Electron cache
        if (window.electronAPI?.cache) {
          const { workingFolders, defaultWorkingFolder } = get();
          window.electronAPI.cache.set('workspace', {
            workingFolders,
            currentWorkingDir: dir,
            defaultWorkingFolder,
          });
        }
        // Sync to backend (same as legacy updateServerWorkingDir)
        if (dir) {
          fetch(`${BASE_URL}/v1/config/working-dir`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ working_dir: dir }),
          }).catch((e) =>
            console.warn('[Settings] Failed to sync working dir:', e),
          );
        }
      },

      migrateSettings: () => {
        const { settings } = get();
        let needsUpdate = false;
        const updated = { ...settings };

        if (updated.model && REMOVED_MODEL_MIGRATION[updated.model]) {
          updated.model = REMOVED_MODEL_MIGRATION[updated.model];
          needsUpdate = true;
          console.log('[Settings Migration] model upgraded to', updated.model);
        }
        if (
          updated.compactModel &&
          REMOVED_MODEL_MIGRATION[updated.compactModel]
        ) {
          updated.compactModel = REMOVED_MODEL_MIGRATION[updated.compactModel];
          needsUpdate = true;
          console.log(
            '[Settings Migration] compactModel upgraded to',
            updated.compactModel,
          );
        }

        // Remove legacy enable1mContext field (1M is now default on Bedrock for Claude 4.x)
        if ('enable1mContext' in updated) {
          delete (updated as Record<string, unknown>).enable1mContext;
          needsUpdate = true;
        }

        if (needsUpdate) {
          set({ settings: updated });
        }
      },

      getEffectiveModel: () => {
        const { settings, defaultModel } = get();
        return settings.model || defaultModel;
      },

      getEffectiveCompactModel: () => {
        const { settings, defaultCompactModel } = get();
        return settings.compactModel || defaultCompactModel;
      },
    }),
    {
      name: 'springo-settings',
      partialize: (state) => ({
        settings: state.settings,
        workingDir: state.workingDir,
        workingFolders: state.workingFolders,
        // defaultWorkingFolder is NOT persisted here — backend (~/.springo/config.json) is the source of truth
      }),
      merge: (persistedState: any, currentState) => {
        const merged = { ...currentState, ...persistedState };
        // Never let stale localStorage override the default — backend is source of truth
        delete (merged as any).defaultWorkingFolder;
        merged.defaultWorkingFolder = currentState.defaultWorkingFolder;
        return merged;
      },
    },
  ),
);

