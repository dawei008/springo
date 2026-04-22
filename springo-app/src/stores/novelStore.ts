/**
 * Springo Novel Mode Store
 *
 * Manages novel project state (chapters/characters/worldbuilding/timeline),
 * persists to the session working directory via the write_file / read_file
 * MCP tools, and hydrates per-session snapshots.
 */
import { create } from 'zustand';
import type {
  NovelProject,
  Chapter,
  Character,
  WorldEntry,
  TimelineEvent,
} from '../components/NovelPanel/types';
import { emptyNovel, countWords, slugify } from '../components/NovelPanel/types';

const BASE_URL = 'http://127.0.0.1:8081';

interface SessionNovelSnapshot {
  active: boolean;
  project: NovelProject;
  activeChapterId: string | null;
  workingDir: string | null;
}

export interface Selection {
  chapterId: string;
  start: number;
  end: number;
}

export interface NovelState {
  active: boolean;
  project: NovelProject;
  activeChapterId: string | null;
  selection: Selection | null;
  workingDir: string | null;
  sessionMap: Record<string, SessionNovelSnapshot>;
  currentSessionId: string | null;
  isLoading: boolean;
  isSaving: boolean;

  activateNovelMode: () => void;
  deactivateNovelMode: () => void;
  toggleNovelMode: () => void;
  switchSession: (sessionId: string | null, workingDir?: string | null) => void;

  setProjectMeta: (patch: Partial<Pick<NovelProject, 'title' | 'synopsis'>>) => void;

  addChapter: (title?: string) => string;
  updateChapter: (id: string, patch: Partial<Chapter>) => void;
  deleteChapter: (id: string) => void;
  reorderChapters: (nextOrder: string[]) => void;
  setActiveChapter: (id: string | null) => void;

  setSelection: (sel: Selection | null) => void;
  applyAIWrite: (chapterId: string, mode: 'replace' | 'append' | 'insert_at', text: string, offset?: number) => void;
  spliceSelection: (chapterId: string, start: number, end: number, replacement: string) => void;

  upsertCharacter: (c: Character) => void;
  deleteCharacter: (name: string) => void;

  upsertWorldEntry: (e: WorldEntry) => void;
  deleteWorldEntry: (topic: string) => void;

  upsertTimelineEvent: (e: TimelineEvent) => void;
  deleteTimelineEvent: (id: string) => void;

  loadFromDisk: (workingDir: string) => Promise<void>;
  saveToDisk: () => Promise<void>;
  scheduleAutosave: () => void;
}

let idCounter = 0;
function newId(prefix: string): string {
  return `${prefix}-${++idCounter}-${Date.now().toString(36)}`;
}

async function execTool(name: string, input: Record<string, unknown>): Promise<Record<string, unknown>> {
  try {
    const res = await fetch(`${BASE_URL}/v1/tools/execute`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, input }),
    });
    const data = await res.json();
    return (data.result as Record<string, unknown>) || data;
  } catch (err) {
    return { error: String(err) };
  }
}

function chapterFilename(ch: Chapter, index: number): string {
  const n = String(index + 1).padStart(3, '0');
  return `chapters/ch${n}-${slugify(ch.title)}.md`;
}

function renderChapterMd(ch: Chapter): string {
  return [
    '---',
    `id: ${ch.id}`,
    `title: ${ch.title}`,
    `status: ${ch.status}`,
    `word_count: ${ch.wordCount}`,
    `updated_at: ${new Date(ch.updatedAt).toISOString()}`,
    '---',
    '',
    ch.content,
  ].join('\n');
}

function parseChapterMd(md: string): { meta: Record<string, string>; body: string } {
  const m = md.match(/^---\n([\s\S]*?)\n---\n?([\s\S]*)$/);
  if (!m) return { meta: {}, body: md };
  const meta: Record<string, string> = {};
  for (const line of m[1].split('\n')) {
    const idx = line.indexOf(':');
    if (idx > 0) meta[line.slice(0, idx).trim()] = line.slice(idx + 1).trim();
  }
  return { meta, body: m[2].replace(/^\n/, '') };
}

let autosaveTimer: ReturnType<typeof setTimeout> | null = null;

export const useNovelStore = create<NovelState>((set, get) => ({
  active: false,
  project: emptyNovel(),
  activeChapterId: null,
  selection: null,
  workingDir: null,
  sessionMap: {},
  currentSessionId: null,
  isLoading: false,
  isSaving: false,

  activateNovelMode: () => set({ active: true }),
  deactivateNovelMode: () => set({ active: false }),
  toggleNovelMode: () => set((s) => ({ active: !s.active })),

  switchSession: (sessionId, workingDir) => {
    const { currentSessionId, active, project, activeChapterId, sessionMap, workingDir: curWD } = get();

    const updatedMap = { ...sessionMap };
    if (currentSessionId) {
      updatedMap[currentSessionId] = { active, project, activeChapterId, workingDir: curWD };
    }

    const restored = sessionId ? updatedMap[sessionId] : null;

    set({
      sessionMap: updatedMap,
      currentSessionId: sessionId,
      active: restored ? restored.active : false,
      project: restored?.project ?? emptyNovel(),
      activeChapterId: restored?.activeChapterId ?? null,
      workingDir: workingDir !== undefined ? workingDir : (restored?.workingDir ?? null),
      selection: null,
    });

    // Auto-load from disk if activating and we have a workingDir but no chapters loaded
    const st = get();
    if (st.active && st.workingDir && st.project.chapterOrder.length === 0) {
      get().loadFromDisk(st.workingDir).catch(() => {});
    }
  },

  setProjectMeta: (patch) => {
    set((s) => ({ project: { ...s.project, ...patch } }));
    get().scheduleAutosave();
  },

  addChapter: (title) => {
    const id = newId('ch');
    const chapter: Chapter = {
      id,
      title: title || `Chapter ${get().project.chapterOrder.length + 1}`,
      status: 'draft',
      content: '',
      wordCount: 0,
      updatedAt: Date.now(),
    };
    set((s) => ({
      project: {
        ...s.project,
        chapters: { ...s.project.chapters, [id]: chapter },
        chapterOrder: [...s.project.chapterOrder, id],
      },
      activeChapterId: id,
    }));
    get().scheduleAutosave();
    return id;
  },

  updateChapter: (id, patch) => {
    set((s) => {
      const current = s.project.chapters[id];
      if (!current) return s;
      const nextContent = patch.content !== undefined ? patch.content : current.content;
      const updated: Chapter = {
        ...current,
        ...patch,
        wordCount: countWords(nextContent),
        updatedAt: Date.now(),
      };
      return {
        project: {
          ...s.project,
          chapters: { ...s.project.chapters, [id]: updated },
        },
      };
    });
    get().scheduleAutosave();
  },

  deleteChapter: (id) => {
    set((s) => {
      const { [id]: _removed, ...rest } = s.project.chapters;
      return {
        project: {
          ...s.project,
          chapters: rest,
          chapterOrder: s.project.chapterOrder.filter((cid) => cid !== id),
        },
        activeChapterId: s.activeChapterId === id ? null : s.activeChapterId,
      };
    });
    get().scheduleAutosave();
  },

  reorderChapters: (nextOrder) => {
    set((s) => ({ project: { ...s.project, chapterOrder: nextOrder } }));
    get().scheduleAutosave();
  },

  setActiveChapter: (id) => set({ activeChapterId: id, selection: null }),

  setSelection: (sel) => set({ selection: sel }),

  applyAIWrite: (chapterId, mode, text, offset) => {
    const ch = get().project.chapters[chapterId];
    if (!ch) return;
    let nextContent = ch.content;
    if (mode === 'replace') {
      nextContent = text;
    } else if (mode === 'append') {
      nextContent = ch.content + (ch.content.endsWith('\n') ? '' : '\n\n') + text;
    } else if (mode === 'insert_at' && offset !== undefined) {
      nextContent = ch.content.slice(0, offset) + text + ch.content.slice(offset);
    }
    get().updateChapter(chapterId, { content: nextContent });
  },

  spliceSelection: (chapterId, start, end, replacement) => {
    const ch = get().project.chapters[chapterId];
    if (!ch) return;
    const next = ch.content.slice(0, start) + replacement + ch.content.slice(end);
    get().updateChapter(chapterId, { content: next });
  },

  upsertCharacter: (c) => {
    set((s) => ({
      project: {
        ...s.project,
        characters: { ...s.project.characters, [c.name]: c },
      },
    }));
    get().scheduleAutosave();
  },

  deleteCharacter: (name) => {
    set((s) => {
      const { [name]: _r, ...rest } = s.project.characters;
      return { project: { ...s.project, characters: rest } };
    });
    get().scheduleAutosave();
  },

  upsertWorldEntry: (e) => {
    set((s) => ({
      project: {
        ...s.project,
        worldbuilding: { ...s.project.worldbuilding, [e.topic]: e },
      },
    }));
    get().scheduleAutosave();
  },

  deleteWorldEntry: (topic) => {
    set((s) => {
      const { [topic]: _r, ...rest } = s.project.worldbuilding;
      return { project: { ...s.project, worldbuilding: rest } };
    });
    get().scheduleAutosave();
  },

  upsertTimelineEvent: (e) => {
    set((s) => {
      const exists = s.project.timeline.some((t) => t.id === e.id);
      const timeline = exists
        ? s.project.timeline.map((t) => (t.id === e.id ? e : t))
        : [...s.project.timeline, e];
      return { project: { ...s.project, timeline } };
    });
    get().scheduleAutosave();
  },

  deleteTimelineEvent: (id) => {
    set((s) => ({
      project: {
        ...s.project,
        timeline: s.project.timeline.filter((t) => t.id !== id),
      },
    }));
    get().scheduleAutosave();
  },

  loadFromDisk: async (workingDir) => {
    if (!workingDir) return;
    set({ isLoading: true });
    try {
      const novelJsonRes = await execTool('read_file', { path: `${workingDir}/novel.json` });
      if (novelJsonRes.error) {
        set({ isLoading: false, workingDir });
        return; // No existing novel yet
      }
      const novel = JSON.parse(String(novelJsonRes.content || '{}')) as {
        title?: string;
        synopsis?: string;
        chapter_order?: string[];
      };

      const chapters: Record<string, Chapter> = {};
      const chapterOrder: string[] = [];
      const order = novel.chapter_order || [];

      for (let i = 0; i < order.length; i++) {
        const cid = order[i];
        // Try common filename patterns (we don't store the exact filename; search by prefix)
        const listRes = await execTool('list_directory', { path: `${workingDir}/chapters`, show_hidden: false });
        const files = (listRes.entries as Array<{ name: string }> | undefined) || [];
        const match = files.find((f) => f.name.startsWith(`ch${String(i + 1).padStart(3, '0')}-`));
        if (!match) continue;
        const mdRes = await execTool('read_file', { path: `${workingDir}/chapters/${match.name}` });
        if (mdRes.error) continue;
        const { meta, body } = parseChapterMd(String(mdRes.content || ''));
        const ch: Chapter = {
          id: meta.id || cid,
          title: meta.title || `Chapter ${i + 1}`,
          status: (meta.status as Chapter['status']) || 'draft',
          content: body,
          wordCount: countWords(body),
          updatedAt: meta.updated_at ? Date.parse(meta.updated_at) : Date.now(),
        };
        chapters[ch.id] = ch;
        chapterOrder.push(ch.id);
      }

      const charsRes = await execTool('read_file', { path: `${workingDir}/characters.json` });
      const worldRes = await execTool('read_file', { path: `${workingDir}/worldbuilding.json` });
      const tlRes = await execTool('read_file', { path: `${workingDir}/timeline.json` });

      const parseJson = <T>(r: Record<string, unknown>, fallback: T): T => {
        if (r.error) return fallback;
        try { return JSON.parse(String(r.content || '')) as T; } catch { return fallback; }
      };

      set({
        project: {
          title: novel.title || 'Untitled Novel',
          synopsis: novel.synopsis || '',
          chapterOrder,
          chapters,
          characters: parseJson<Record<string, Character>>(charsRes, {}),
          worldbuilding: parseJson<Record<string, WorldEntry>>(worldRes, {}),
          timeline: parseJson<TimelineEvent[]>(tlRes, []),
        },
        workingDir,
        isLoading: false,
        activeChapterId: chapterOrder[0] || null,
      });
    } catch (err) {
      console.warn('[novelStore] loadFromDisk failed', err);
      set({ isLoading: false, workingDir });
    }
  },

  saveToDisk: async () => {
    const { workingDir, project } = get();
    if (!workingDir) return;
    set({ isSaving: true });
    try {
      await execTool('create_directory', { path: `${workingDir}/chapters` });

      // novel.json
      await execTool('write_file', {
        path: `${workingDir}/novel.json`,
        content: JSON.stringify(
          {
            title: project.title,
            synopsis: project.synopsis,
            chapter_order: project.chapterOrder,
          },
          null,
          2,
        ),
      });

      // chapters/*.md
      for (let i = 0; i < project.chapterOrder.length; i++) {
        const cid = project.chapterOrder[i];
        const ch = project.chapters[cid];
        if (!ch) continue;
        await execTool('write_file', {
          path: `${workingDir}/${chapterFilename(ch, i)}`,
          content: renderChapterMd(ch),
        });
      }

      // characters, world, timeline
      await execTool('write_file', {
        path: `${workingDir}/characters.json`,
        content: JSON.stringify(project.characters, null, 2),
      });
      await execTool('write_file', {
        path: `${workingDir}/worldbuilding.json`,
        content: JSON.stringify(project.worldbuilding, null, 2),
      });
      await execTool('write_file', {
        path: `${workingDir}/timeline.json`,
        content: JSON.stringify(project.timeline, null, 2),
      });
    } catch (err) {
      console.warn('[novelStore] saveToDisk failed', err);
    } finally {
      set({ isSaving: false });
    }
  },

  scheduleAutosave: () => {
    if (autosaveTimer) clearTimeout(autosaveTimer);
    autosaveTimer = setTimeout(() => {
      get().saveToDisk().catch(() => {});
    }, 2000);
  },
}));

if (typeof window !== 'undefined') (window as any).__novelStore = useNovelStore;
