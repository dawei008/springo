import { create } from 'zustand';
import { useSettingsStore } from './settingsStore';

const BASE_URL = 'http://127.0.0.1:8081';
const NEWS_REFRESH_INTERVAL = 60 * 60 * 1000; // 1 hour

export interface NewsItem {
  topic: string;
  title: string;
  description: string;
  source: string;
  publishedAt: string;
  url: string;
}

interface NewsState {
  interests: string[];
  newsItems: NewsItem[];
  loading: boolean;
  lastUpdated: Date | null;
  refreshing: boolean;

  loadInterests: () => Promise<void>;
  removeInterest: (interest: string) => Promise<void>;
  refreshNews: (force?: boolean) => Promise<void>;
  initNews: () => void;
  cleanup: () => void;
}

let pollingTimer: ReturnType<typeof setTimeout> | null = null;
let refreshInterval: ReturnType<typeof setInterval> | null = null;

export const useNewsStore = create<NewsState>((set, get) => ({
  interests: [],
  newsItems: [],
  loading: false,
  lastUpdated: null,
  refreshing: false,

  loadInterests: async () => {
    try {
      const res = await fetch(`${BASE_URL}/v1/news/interests`);
      const data = await res.json();
      set({ interests: data.interests || [] });
    } catch (e) {
      console.error('[News] Failed to load interests:', (e as Error).message);
    }
  },

  removeInterest: async (interest: string) => {
    try {
      await fetch(
        `${BASE_URL}/v1/news/interests/${encodeURIComponent(interest)}`,
        { method: 'DELETE' },
      );
      await get().loadInterests();
      // Force refresh news with updated interests
      get().refreshNews(true);
    } catch (e) {
      console.error('[News] Failed to remove interest:', (e as Error).message);
    }
  },

  refreshNews: async (force = false) => {
    set({ refreshing: true });

    // Show loading state only when we have no cached items
    if (get().newsItems.length === 0) {
      set({ loading: true });
    }

    try {
      const model = useSettingsStore.getState().settings.model || useSettingsStore.getState().defaultModel;
      const m = encodeURIComponent(model);
      const url = force
        ? `${BASE_URL}/v1/news/fetch?force=true&model=${m}`
        : `${BASE_URL}/v1/news/fetch?model=${m}`;

      const response = await fetch(url);
      const data = await response.json();

      // Handle async loading status — poll every 3 seconds
      if (data.status === 'loading') {
        // Show cached news if available while loading
        if (data.news && data.news.length > 0) {
          set({ newsItems: data.news });
        }
        // Start polling if not already
        if (!pollingTimer) {
          pollingTimer = setTimeout(() => {
            pollingTimer = null;
            get().refreshNews();
          }, 3000);
        }
        return; // Keep refreshing state active
      }

      // Clear polling timer on success or non-loading response
      if (pollingTimer) {
        clearTimeout(pollingTimer);
        pollingTimer = null;
      }

      if (data.success && data.news && data.news.length > 0) {
        set({
          newsItems: data.news,
          lastUpdated: data.timestamp ? new Date(data.timestamp) : new Date(),
          loading: false,
          refreshing: false,
        });
      } else {
        set({ loading: false, refreshing: false });
      }
    } catch (e) {
      console.error('[News] Failed to refresh news:', (e as Error).message);
      // Clear polling on error
      if (pollingTimer) {
        clearTimeout(pollingTimer);
        pollingTimer = null;
      }
      set({ loading: false, refreshing: false });
    }
  },

  initNews: () => {
    const { loadInterests, refreshNews } = get();
    loadInterests();
    refreshNews();

    // Set up 1-hour auto-refresh
    if (refreshInterval) {
      clearInterval(refreshInterval);
    }
    refreshInterval = setInterval(() => {
      get().refreshNews();
    }, NEWS_REFRESH_INTERVAL);
  },

  cleanup: () => {
    if (pollingTimer) {
      clearTimeout(pollingTimer);
      pollingTimer = null;
    }
    if (refreshInterval) {
      clearInterval(refreshInterval);
      refreshInterval = null;
    }
  },
}));

/**
 * Format a time string into a relative time display.
 * Handles both ISO date strings and pre-formatted relative strings.
 */
export function formatNewsTime(timeStr: string): string {
  if (!timeStr) return '';

  // If it's already a relative time string (e.g., "2 hours ago")
  if (
    timeStr.includes('ago') ||
    timeStr.includes('hour') ||
    timeStr.includes('day') ||
    timeStr.includes('minute')
  ) {
    return timeStr;
  }

  // Try to parse as date
  try {
    const date = new Date(timeStr);
    if (isNaN(date.getTime())) return timeStr;

    const now = new Date();
    const diff = now.getTime() - date.getTime();
    const hours = Math.floor(diff / (1000 * 60 * 60));
    const days = Math.floor(hours / 24);

    if (hours < 1) return 'Just now';
    if (hours < 24) return `${hours}h ago`;
    if (days < 7) return `${days}d ago`;
    return date.toLocaleDateString();
  } catch {
    return timeStr;
  }
}
