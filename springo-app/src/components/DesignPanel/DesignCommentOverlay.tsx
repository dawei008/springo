import { useState, useCallback } from 'react';
import { useDesignStore, type DesignComment } from '@/stores/designStore';

export default function DesignCommentOverlay() {
  const interactionMode = useDesignStore((s) => s.interactionMode);
  const comments = useDesignStore((s) => s.comments);
  const addComment = useDesignStore((s) => s.addComment);
  const removeComment = useDesignStore((s) => s.removeComment);
  const [pendingPos, setPendingPos] = useState<{ x: number; y: number } | null>(null);
  const [commentText, setCommentText] = useState('');
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const handleClick = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
    if (interactionMode !== 'comment') return;
    const rect = e.currentTarget.getBoundingClientRect();
    const x = ((e.clientX - rect.left) / rect.width) * 100;
    const y = ((e.clientY - rect.top) / rect.height) * 100;
    setPendingPos({ x, y });
    setCommentText('');
  }, [interactionMode]);

  const handleSubmit = useCallback(() => {
    if (!pendingPos || !commentText.trim()) return;
    const comment: DesignComment = {
      id: `comment-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      x: pendingPos.x,
      y: pendingPos.y,
      text: commentText.trim(),
      author: 'You',
      timestamp: Date.now(),
    };
    addComment(comment);
    setPendingPos(null);
    setCommentText('');
  }, [pendingPos, commentText, addComment]);

  if (interactionMode !== 'comment' && comments.length === 0) return null;

  return (
    <div
      className={`design-comment-overlay${interactionMode === 'comment' ? ' active' : ''}`}
      onClick={handleClick}
    >
      {comments.map((c) => (
        <div
          key={c.id}
          className={`design-comment-pin${expandedId === c.id ? ' expanded' : ''}${c.resolved ? ' resolved' : ''}`}
          style={{ left: `${c.x}%`, top: `${c.y}%` }}
          onClick={(e) => { e.stopPropagation(); setExpandedId(expandedId === c.id ? null : c.id); }}
        >
          <div className="design-comment-pin-dot">
            <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
          </div>
          {expandedId === c.id && (
            <div className="design-comment-bubble">
              <div className="design-comment-author">{c.author}</div>
              <div className="design-comment-text">{c.text}</div>
              <div className="design-comment-actions">
                <button onClick={(e) => { e.stopPropagation(); removeComment(c.id); setExpandedId(null); }}>Delete</button>
              </div>
            </div>
          )}
        </div>
      ))}

      {pendingPos && (
        <div
          className="design-comment-pin expanded"
          style={{ left: `${pendingPos.x}%`, top: `${pendingPos.y}%` }}
          onClick={(e) => e.stopPropagation()}
        >
          <div className="design-comment-pin-dot pending">
            <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
          </div>
          <div className="design-comment-bubble">
            <textarea
              className="design-comment-input"
              value={commentText}
              onChange={(e) => setCommentText(e.target.value)}
              placeholder="Add a comment..."
              autoFocus
              onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSubmit(); } if (e.key === 'Escape') setPendingPos(null); }}
            />
            <div className="design-comment-actions">
              <button onClick={() => setPendingPos(null)}>Cancel</button>
              <button className="primary" onClick={handleSubmit} disabled={!commentText.trim()}>Post</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
