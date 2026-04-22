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
import { api } from '../services/api';
import { useSessionStore } from './sessionStore';

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

/**
 * Tracks what the user last asked the AI to do, so the editor's
 * "Apply AI reply" button knows where to splice/append the result.
 */
export interface PendingAIIntent {
  kind: 'continue' | 'rewrite';
  chapterId: string;
  /** Only set for 'rewrite': the selection bounds at the time of request. */
  start?: number;
  end?: number;
  /** Message count at the time the intent was issued, so Apply can detect fresh replies. */
  baselineMessageCount: number;
  /** Timestamp for display ("pending since …"). */
  createdAt: number;
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
  pendingAIIntent: PendingAIIntent | null;

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
  setPendingAIIntent: (intent: PendingAIIntent | null) => void;
  applyAIWrite: (chapterId: string, mode: 'replace' | 'append' | 'insert_at', text: string, offset?: number) => void;
  spliceSelection: (chapterId: string, start: number, end: number, replacement: string) => void;

  /** Concatenated word count of every chapter. */
  totalWordCount: () => number;

  /** Export the whole novel as a single markdown string (returns path written). */
  exportAsMarkdown: () => Promise<string | null>;

  /**
   * Import one or more .md files as chapters.
   * Each file becomes a new chapter appended to chapterOrder. Existing
   * frontmatter (id/title/status) is respected; otherwise the filename (minus
   * extension) is used as the title and status defaults to "draft".
   *
   * Accepts File objects (from an <input type="file">) or { name, content }
   * pairs. Returns the ids of newly-added chapters in order.
   */
  importChaptersFromFiles: (
    files: ReadonlyArray<File | { name: string; content: string }>,
  ) => Promise<string[]>;

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
    const res = await api.tools.execute(name, input);
    if (!res.ok || !res.data) return { error: res.error || 'unknown error' };
    return res.data.result || {};
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

/**
 * Matches a Markdown H2 that looks like a chapter/episode/section marker.
 * Supports Chinese ("第 9 集：...", "第1章 XXX", "第3回 XXX", "第5话 XXX")
 * and English ("Chapter 3 — ..."). Non-chapter H2s (like "附录" or
 * "修订对照总览") are deliberately *not* matched, so they fold into the
 * preceding chapter instead of becoming their own nodes.
 */
const CHAPTER_H2_RE =
  /^##\s+(?:(?:第\s*[0-9零一二三四五六七八九十百千两]+\s*[集章回节卷部篇幕话].*)|(?:Chapter\s+\d+.*)|(?:Episode\s+\d+.*))$/i;

/**
 * Split a markdown body into chapter sections by scanning for chapter-pattern
 * H2 headings. Content before the first chapter heading is returned as
 * `preamble`. Non-chapter H2s between two chapter headings remain part of
 * the earlier chapter's content (they become subsections of that chapter).
 *
 * If no chapter headings are found, returns `{ preamble: body, chapters: [] }`
 * so the caller can fall back to "one chapter per file".
 */
function splitByChapterHeadings(body: string): {
  preamble: string;
  chapters: Array<{ title: string; content: string }>;
} {
  const lines = body.split('\n');
  const chapters: Array<{ title: string; content: string }> = [];
  const preambleLines: string[] = [];
  let currentTitle: string | null = null;
  let currentLines: string[] = [];

  for (const line of lines) {
    if (CHAPTER_H2_RE.test(line)) {
      // Flush previous chapter
      if (currentTitle !== null) {
        chapters.push({ title: currentTitle, content: currentLines.join('\n').trim() });
      }
      currentTitle = line.replace(/^##\s+/, '').trim();
      currentLines = [];
    } else if (currentTitle === null) {
      preambleLines.push(line);
    } else {
      currentLines.push(line);
    }
  }
  if (currentTitle !== null) {
    chapters.push({ title: currentTitle, content: currentLines.join('\n').trim() });
  }
  return { preamble: preambleLines.join('\n').trim(), chapters };
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
  pendingAIIntent: null,

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

    // If no prior snapshot exists, infer active from the session's own mode —
    // a freshly-created `mode: 'novel'` session should open the novel panel
    // immediately, without waiting for the user to re-toggle the mode.
    let nextActive: boolean;
    if (restored) {
      nextActive = restored.active;
    } else if (sessionId) {
      const sessions = useSessionStore.getState().sessions;
      const sess = sessions.find((s) => s.id === sessionId);
      nextActive = sess?.mode === 'novel';
    } else {
      nextActive = false;
    }

    set({
      sessionMap: updatedMap,
      currentSessionId: sessionId,
      active: nextActive,
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

  setPendingAIIntent: (intent) => set({ pendingAIIntent: intent }),

  totalWordCount: () => {
    const { project } = get();
    return project.chapterOrder.reduce((sum, cid) => {
      const ch = project.chapters[cid];
      return sum + (ch?.wordCount || 0);
    }, 0);
  },

  exportAsMarkdown: async () => {
    const { project, workingDir } = get();
    if (!workingDir) return null;
    const parts: string[] = [];
    parts.push(`# ${project.title}`);
    if (project.synopsis) parts.push(`\n> ${project.synopsis.split('\n').join('\n> ')}`);
    parts.push('');
    for (const cid of project.chapterOrder) {
      const ch = project.chapters[cid];
      if (!ch) continue;
      parts.push(`\n## ${ch.title}\n`);
      parts.push(ch.content);
    }
    const outputPath = `${workingDir}/${slugify(project.title || 'novel')}-export.md`;
    await execTool('write_file', {
      path: outputPath,
      content: parts.join('\n'),
    });
    return outputPath;
  },

  importChaptersFromFiles: async (files) => {
    const newIds: string[] = [];
    for (const f of files) {
      // Read content — handle both File and {name, content}
      let rawName: string;
      let raw: string;
      if ('text' in f && typeof f.text === 'function') {
        rawName = f.name;
        raw = await f.text();
      } else {
        rawName = (f as { name: string; content: string }).name;
        raw = (f as { name: string; content: string }).content;
      }

      // Strip extension + directory prefix from filename for a fallback title
      const baseName = rawName.replace(/^.*[\\/]/, '').replace(/\.(md|markdown)$/i, '');

      // If file has our own frontmatter, honor id/title/status; otherwise
      // derive title from filename and fall back to the first H1/H2 inside.
      const parsed = parseChapterMd(raw);
      const fmTitle = parsed.meta.title?.trim();
      const status = (parsed.meta.status as Chapter['status']) || 'draft';

      // Try to split the body by chapter-pattern H2 headings
      // ("## 第 9 集：...", "## Chapter 3 — ..."). If any are found, each
      // becomes its own chapter. Otherwise fall back to one chapter per file.
      const { preamble, chapters: sections } = splitByChapterHeadings(parsed.body);

      const chaptersToAdd: Array<{ title: string; content: string }> = [];
      if (sections.length > 0) {
        // If there's meaningful preamble (e.g., a file-level intro or
        // "修订对照总览"), keep it as a leading "前言" chapter so the user
        // doesn't lose it. Empty / whitespace-only preambles are dropped.
        if (preamble && countWords(preamble) > 20) {
          chaptersToAdd.push({
            title: fmTitle || baseName || '前言',
            content: preamble,
          });
        }
        for (const sec of sections) {
          // Clean up title: "第 9 集：保险柜的密码" → keep as-is.
          chaptersToAdd.push({ title: sec.title, content: sec.content });
        }
      } else {
        // No chapter headings — whole file becomes one chapter.
        const bodyFirstHeading = parsed.body.match(/^#+\s+(.+)$/m)?.[1]?.trim();
        chaptersToAdd.push({
          title: fmTitle || bodyFirstHeading || baseName || '未命名章节',
          content: parsed.body,
        });
      }

      for (const { title, content } of chaptersToAdd) {
        const id = newId('ch');
        const chapter: Chapter = {
          id,
          title,
          status,
          content,
          wordCount: countWords(content),
          updatedAt: Date.now(),
        };
        set((s) => ({
          project: {
            ...s.project,
            chapters: { ...s.project.chapters, [id]: chapter },
            chapterOrder: [...s.project.chapterOrder, id],
          },
          // Activate the first imported chapter so the user sees feedback
          activeChapterId: newIds.length === 0 ? id : s.activeChapterId,
        }));
        newIds.push(id);
      }
    }
    if (newIds.length > 0) get().scheduleAutosave();
    return newIds;
  },

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

      const listRes = await execTool('list_directory', { path: `${workingDir}/chapters`, show_hidden: false });
      const dirFiles = (listRes.entries as Array<{ name: string }> | undefined) || [];

      const chapterResults = await Promise.all(
        order.map(async (cid, i) => {
          const match = dirFiles.find((f) => f.name.startsWith(`ch${String(i + 1).padStart(3, '0')}-`));
          if (!match) return null;
          const mdRes = await execTool('read_file', { path: `${workingDir}/chapters/${match.name}` });
          if (mdRes.error) return null;
          const { meta, body } = parseChapterMd(String(mdRes.content || ''));
          return {
            id: meta.id || cid,
            title: meta.title || `Chapter ${i + 1}`,
            status: (meta.status as Chapter['status']) || 'draft',
            content: body,
            wordCount: countWords(body),
            updatedAt: meta.updated_at ? Date.parse(meta.updated_at) : Date.now(),
          } as Chapter;
        }),
      );

      for (const ch of chapterResults) {
        if (!ch) continue;
        chapters[ch.id] = ch;
        chapterOrder.push(ch.id);
      }

      const [charsRes, worldRes, tlRes] = await Promise.all([
        execTool('read_file', { path: `${workingDir}/characters.json` }),
        execTool('read_file', { path: `${workingDir}/worldbuilding.json` }),
        execTool('read_file', { path: `${workingDir}/timeline.json` }),
      ]);

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
