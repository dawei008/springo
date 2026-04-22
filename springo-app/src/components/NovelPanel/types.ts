export type ChapterStatus = 'draft' | 'revising' | 'done';

export interface Chapter {
  id: string;
  title: string;
  status: ChapterStatus;
  content: string;
  wordCount: number;
  updatedAt: number;
}

export interface Character {
  name: string;
  role?: string;
  appearance?: string;
  motivation?: string;
  arc?: string;
  notes?: string;
}

export interface WorldEntry {
  topic: string;
  content: string;
}

export interface TimelineEvent {
  id: string;
  when: string;
  chapterId?: string;
  description: string;
}

export interface NovelProject {
  title: string;
  synopsis: string;
  chapterOrder: string[];
  chapters: Record<string, Chapter>;
  characters: Record<string, Character>;
  worldbuilding: Record<string, WorldEntry>;
  timeline: TimelineEvent[];
}

export function emptyNovel(): NovelProject {
  return {
    title: 'Untitled Novel',
    synopsis: '',
    chapterOrder: [],
    chapters: {},
    characters: {},
    worldbuilding: {},
    timeline: [],
  };
}

export function countWords(text: string): number {
  if (!text) return 0;
  const cjk = (text.match(/[\u4e00-\u9fff\u3400-\u4dbf]/g) || []).length;
  const words = (text.match(/[A-Za-z0-9]+(?:['-][A-Za-z0-9]+)*/g) || []).length;
  return cjk + words;
}

export function slugify(input: string): string {
  const cleaned = input.toLowerCase().trim().replace(/[^\p{L}\p{N}\s-]/gu, '').replace(/\s+/g, '-');
  return cleaned.slice(0, 40) || 'untitled';
}
