/**
 * NovelEditor — center column. Textarea + word count + AI action buttons.
 *
 * AI interaction pattern: the user clicks "续写" or "改写选区", which
 *   1. Records a PendingAIIntent in novelStore (so we know where to splice)
 *   2. Prefills the chat input via uiStore.pendingPrompt with rich context
 *   3. User sends, AI replies in chat with plain prose
 *   4. User clicks "应用回复" to splice/append the AI's reply into the chapter
 *
 * No custom backend tools required — works with any model, any vendor.
 */
import { useRef, useCallback, useEffect, useState } from 'react';
import { useNovelStore } from '@/stores/novelStore';
import { useUIStore } from '@/stores/uiStore';
import { useChatStore } from '@/stores/chatStore';
import { useSessionStore } from '@/stores/sessionStore';
import Markdown from '@/components/common/Markdown';
import type { Message } from '@/types';

/** Extract the last assistant text message after `baselineCount` messages. */
function extractLatestAssistantText(messages: Message[], baselineCount: number): string | null {
  for (let i = messages.length - 1; i >= baselineCount; i--) {
    const msg = messages[i];
    if (msg.role !== 'assistant' || msg.isThinking) continue;
    if (typeof msg.content === 'string' && msg.content.trim()) return msg.content.trim();
    if (Array.isArray(msg.content)) {
      const text = msg.content
        .filter((b): b is { type: 'text'; text: string } =>
          typeof b === 'object' && b !== null && (b as { type?: string }).type === 'text',
        )
        .map((b) => b.text)
        .join('\n')
        .trim();
      if (text) return text;
    }
  }
  return null;
}

/** Strip author preamble ("这是我的改写：", "Here is the continuation:", etc.) */
function cleanProseReply(raw: string): string {
  let s = raw.trim();
  // Strip leading markdown code fence
  s = s.replace(/^```[a-zA-Z]*\n/, '').replace(/\n```$/, '');
  // Strip conversational preamble before first blank line or paragraph break
  const preambleRe = /^(.{0,120}?)(?:\n\n)/;
  const m = s.match(preambleRe);
  if (m && /[:：]\s*$/.test(m[1])) {
    s = s.slice(m[0].length);
  }
  return s.trim();
}

export default function NovelEditor() {
  const activeChapterId = useNovelStore((s) => s.activeChapterId);
  const chapter = useNovelStore((s) =>
    s.activeChapterId ? s.project.chapters[s.activeChapterId] : null,
  );
  const project = useNovelStore((s) => s.project);
  const updateChapter = useNovelStore((s) => s.updateChapter);
  const setSelection = useNovelStore((s) => s.setSelection);
  const saveToDisk = useNovelStore((s) => s.saveToDisk);
  const isSaving = useNovelStore((s) => s.isSaving);
  const pendingAIIntent = useNovelStore((s) => s.pendingAIIntent);
  const setPendingAIIntent = useNovelStore((s) => s.setPendingAIIntent);
  const applyAIWrite = useNovelStore((s) => s.applyAIWrite);
  const spliceSelection = useNovelStore((s) => s.spliceSelection);
  const setActiveChapter = useNovelStore((s) => s.setActiveChapter);

  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const [preview, setPreview] = useState(false);
  const [selectionText, setSelectionText] = useState('');

  // Keep selection in store whenever textarea selection changes
  const onSelect = useCallback(() => {
    const el = textareaRef.current;
    if (!el || !activeChapterId) return;
    const { selectionStart: start, selectionEnd: end } = el;
    if (start !== end) {
      setSelection({ chapterId: activeChapterId, start, end });
      setSelectionText(el.value.slice(start, end));
    } else {
      setSelection(null);
      setSelectionText('');
    }
  }, [activeChapterId, setSelection]);

  // Clear selection-text when switching chapter
  useEffect(() => {
    setSelectionText('');
    setSelection(null);
  }, [activeChapterId, setSelection]);

  /** Build a short context block that prefixes every AI prompt. */
  const buildContext = useCallback(() => {
    if (!chapter) return '';
    const lines: string[] = [];
    lines.push(`# 作品：${project.title}`);
    if (project.synopsis) lines.push(`梗概：${project.synopsis.replace(/\s+/g, ' ').slice(0, 400)}`);
    const chars = Object.values(project.characters);
    if (chars.length > 0) {
      const names = chars
        .slice(0, 8)
        .map((c) => (c.role ? `${c.name}（${c.role}）` : c.name))
        .join('、');
      lines.push(`主要人物：${names}`);
    }
    lines.push(`当前章节：${chapter.title}（${chapter.status} · ${chapter.wordCount} 字）`);
    return lines.join('\n');
  }, [chapter, project]);

  const handleContinue = useCallback(() => {
    if (!chapter) return;
    const sessionId = useSessionStore.getState().currentSessionId;
    if (!sessionId) return;
    const runtime = useChatStore.getState().runtimes[sessionId];
    const baseline = runtime?.messages.length ?? 0;

    const prev = chapter.content.slice(-600);
    const ctx = buildContext();
    const prompt =
      `${ctx}\n\n` +
      `## 任务：续写\n` +
      `请从下面的结尾自然地往下写一段（约 300-600 字），保持同一视角、同一时态、同一语气。\n` +
      `**只输出新的正文内容**，不要开头语、不要"好的"/"以下是"这类回复词，不要再重复已有的段落。\n\n` +
      (prev ? `### 已有结尾\n\n${prev}\n\n### 续写：` : '### （空章节，请从头开始写第一幕场景）');

    setPendingAIIntent({
      kind: 'continue',
      chapterId: chapter.id,
      baselineMessageCount: baseline,
      createdAt: Date.now(),
    });
    useUIStore.getState().setPendingPrompt(prompt);
  }, [chapter, buildContext, setPendingAIIntent]);

  const handleRewrite = useCallback(() => {
    if (!chapter || !selectionText) return;
    const el = textareaRef.current;
    if (!el) return;
    const { selectionStart: start, selectionEnd: end } = el;
    const sessionId = useSessionStore.getState().currentSessionId;
    if (!sessionId) return;
    const runtime = useChatStore.getState().runtimes[sessionId];
    const baseline = runtime?.messages.length ?? 0;

    const ctx = buildContext();
    const prompt =
      `${ctx}\n\n` +
      `## 任务：改写选区\n` +
      `请将下面这段文字改写（可以润色 / 换视角 / 变节奏 / 加感官细节，根据我下面的要求）。\n` +
      `**只输出改写后的文字本身**，不要解释。字数与原文大致相当。\n\n` +
      `### 原文\n\n${selectionText}\n\n` +
      `### 改写方向\n（在这里写：例如 "更紧张、更简短"、"换成第一人称"、"加入视觉与听觉细节"）`;

    setPendingAIIntent({
      kind: 'rewrite',
      chapterId: chapter.id,
      start,
      end,
      baselineMessageCount: baseline,
      createdAt: Date.now(),
    });
    useUIStore.getState().setPendingPrompt(prompt);
  }, [chapter, selectionText, buildContext, setPendingAIIntent]);

  /** Apply the most recent assistant reply to the chapter per the pending intent. */
  const handleApplyReply = useCallback(() => {
    if (!pendingAIIntent) return;

    // Always pull the target chapter from the store (not the `chapter` memo),
    // so "apply" works even when the user is currently viewing a different
    // chapter. We still switch the view to the target so the highlight lands
    // in the visible editor.
    const store = useNovelStore.getState();
    const targetChapter = store.project.chapters[pendingAIIntent.chapterId];
    if (!targetChapter) {
      alert('目标章节已不存在（可能被删除）。');
      setPendingAIIntent(null);
      return;
    }

    const needsSwitch = store.activeChapterId !== pendingAIIntent.chapterId;
    if (needsSwitch) setActiveChapter(pendingAIIntent.chapterId);

    const sessionId = useSessionStore.getState().currentSessionId;
    if (!sessionId) return;
    const runtime = useChatStore.getState().runtimes[sessionId];
    if (!runtime) return;

    const raw = extractLatestAssistantText(runtime.messages, pendingAIIntent.baselineMessageCount);
    if (!raw) {
      alert('还没找到 AI 的新回复，请先发送请求并等待回复完成。');
      return;
    }
    const clean = cleanProseReply(raw);

    // Compute the selection range of the newly inserted text so we can
    // scroll the textarea and visually highlight it — otherwise "apply" looks
    // silent because content goes at the end / middle of a long textarea.
    const beforeContent = targetChapter.content;
    let insertStart = 0;
    let insertEnd = 0;

    if (pendingAIIntent.kind === 'continue') {
      applyAIWrite(targetChapter.id, 'append', clean);
      const sep = beforeContent.endsWith('\n') || !beforeContent ? '' : '\n\n';
      insertStart = beforeContent.length + sep.length;
      insertEnd = insertStart + clean.length;
    } else if (pendingAIIntent.kind === 'rewrite' &&
               pendingAIIntent.start !== undefined &&
               pendingAIIntent.end !== undefined) {
      spliceSelection(targetChapter.id, pendingAIIntent.start, pendingAIIntent.end, clean);
      insertStart = pendingAIIntent.start;
      insertEnd = pendingAIIntent.start + clean.length;
    }
    setPendingAIIntent(null);

    // If we're in preview mode, jump to edit mode so the user can see / tweak
    // the newly-applied prose.
    if (preview) setPreview(false);

    // After React re-renders the textarea with the new value, scroll to
    // the insertion range and select it. Use multiple rAFs so both the
    // chapter switch (if any) and the content update have painted.
    const scrollAndHighlight = () => {
      const el = textareaRef.current;
      if (!el) return;
      // Only do this if the textarea now reflects the target chapter.
      if (el.value !== useNovelStore.getState().project.chapters[pendingAIIntent.chapterId]?.content) {
        // Not painted yet — try again next frame.
        requestAnimationFrame(scrollAndHighlight);
        return;
      }
      el.focus();
      try {
        el.setSelectionRange(insertStart, insertEnd);
      } catch {
        /* noop */
      }
      const lineHeight = parseInt(getComputedStyle(el).lineHeight || '22', 10) || 22;
      const beforeNewline = el.value.slice(0, insertStart).split('\n').length - 1;
      const targetTop = Math.max(0, beforeNewline * lineHeight - el.clientHeight / 3);
      el.scrollTop = targetTop;
    };
    requestAnimationFrame(() => requestAnimationFrame(scrollAndHighlight));
  }, [pendingAIIntent, applyAIWrite, spliceSelection, setPendingAIIntent, setActiveChapter, preview]);

  if (!chapter) {
    return (
      <div className="novel-editor-empty">
        <div>选择一个章节开始写作</div>
        <div className="novel-editor-empty-hint">
          左侧点击章节，或点击 <strong>+</strong> 新建第一章。
        </div>
      </div>
    );
  }

  const hasPending = !!pendingAIIntent;
  const pendingForThisChapter = !!(pendingAIIntent && pendingAIIntent.chapterId === chapter.id);
  const pendingChapterTitle = pendingAIIntent
    ? project.chapters[pendingAIIntent.chapterId]?.title
    : null;

  return (
    <div className="novel-editor">
      <div className="novel-editor-header">
        <input
          type="text"
          className="novel-editor-title"
          value={chapter.title}
          onChange={(e) => updateChapter(chapter.id, { title: e.target.value })}
          placeholder="章节标题"
        />
        <div className="novel-editor-actions">
          <select
            value={chapter.status}
            onChange={(e) => updateChapter(chapter.id, { status: e.target.value as 'draft' | 'revising' | 'done' })}
            className="novel-status-select"
          >
            <option value="draft">草稿</option>
            <option value="revising">修订中</option>
            <option value="done">已完成</option>
          </select>
          <button
            className={`novel-mode-toggle${preview ? ' active' : ''}`}
            onClick={() => setPreview((p) => !p)}
            title="切换预览"
          >
            {preview ? '✎ 编辑' : '👁 预览'}
          </button>
        </div>
      </div>

      {preview ? (
        <div className="novel-editor-preview">
          <Markdown content={chapter.content || '*（空章节）*'} />
        </div>
      ) : (
        <textarea
          ref={textareaRef}
          className="novel-editor-textarea"
          value={chapter.content}
          onChange={(e) => updateChapter(chapter.id, { content: e.target.value })}
          onSelect={onSelect}
          onKeyUp={onSelect}
          onMouseUp={onSelect}
          placeholder="在这里开始你的故事……&#10;&#10;提示：&#10;• 选中一段文字后点「改写选区」，AI 会在对话里回复改写版，然后点「应用回复」即可替换&#10;• 点「续写」让 AI 从光标后续写&#10;• 支持 Markdown 语法"
          spellCheck={false}
        />
      )}

      {hasPending && (
        <div className="novel-pending-banner">
          <span>
            ⏳ 等待 AI {pendingAIIntent!.kind === 'continue' ? '续写' : '改写'}
            {!pendingForThisChapter && pendingChapterTitle && (
              <> 「{pendingChapterTitle}」</>
            )}
            … 回复到达后点 <strong>应用回复</strong> 即可写入章节
          </span>
          <button className="novel-pending-cancel" onClick={() => setPendingAIIntent(null)}>
            取消
          </button>
        </div>
      )}

      <div className="novel-editor-footer">
        <div className="novel-editor-stats">
          <span>{chapter.wordCount} 字</span>
          {selectionText && <span>· 选中 {selectionText.length} 字符</span>}
          <span className={`novel-save-indicator${isSaving ? ' saving' : ''}`}>
            {isSaving ? '● 保存中' : '● 已保存'}
          </span>
        </div>
        <div className="novel-editor-ai-actions">
          {hasPending && (
            <button
              className="novel-ai-btn apply"
              onClick={handleApplyReply}
              title={
                pendingForThisChapter
                  ? '把对话里最新一条 AI 回复应用到本章末尾'
                  : `应用到「${pendingChapterTitle ?? '目标章节'}」（会自动切过去）`
              }
            >
              ✨ 应用回复{!pendingForThisChapter && pendingChapterTitle ? ` → ${pendingChapterTitle}` : ''}
            </button>
          )}
          <button
            className="novel-ai-btn"
            onClick={handleRewrite}
            disabled={!selectionText}
            title={selectionText ? '让 AI 改写选中段落' : '先在正文中选中一段文字'}
          >
            ✎ 改写选区
          </button>
          <button
            className="novel-ai-btn primary"
            onClick={handleContinue}
            title="从当前位置让 AI 续写"
          >
            ▶ 续写
          </button>
          <button
            className="novel-ai-btn"
            onClick={() => saveToDisk().catch(() => {})}
            title="立即保存到磁盘"
          >
            ⬇ 保存
          </button>
        </div>
      </div>
    </div>
  );
}
