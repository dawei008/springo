import { useEffect, useState, useCallback } from 'react';
import { useNewsStore, formatNewsTime } from '../../stores/newsStore';
import type { NewsItem } from '../../stores/newsStore';

// ─── Drag hint icon (grip dots) ───

function DragHintIcon() {
  return (
    <svg className="news-drag-hint" width="10" height="14" viewBox="0 0 10 14" fill="var(--text-tertiary)">
      <circle cx="3" cy="2" r="1.2" />
      <circle cx="7" cy="2" r="1.2" />
      <circle cx="3" cy="7" r="1.2" />
      <circle cx="7" cy="7" r="1.2" />
      <circle cx="3" cy="12" r="1.2" />
      <circle cx="7" cy="12" r="1.2" />
    </svg>
  );
}

// ─── News Item ───

function NewsItemCard({ item }: { item: NewsItem }) {
  const [dragging, setDragging] = useState(false);

  const handleDragStart = useCallback((e: React.DragEvent) => {
    setDragging(true);
    e.dataTransfer.setData(
      'application/x-springo-news',
      JSON.stringify(item),
    );
    e.dataTransfer.effectAllowed = 'copy';
  }, [item]);

  const handleDragEnd = useCallback(() => {
    setDragging(false);
  }, []);

  return (
    <div
      className={`news-item${dragging ? ' dragging' : ''}`}
      draggable
      onDragStart={handleDragStart}
      onDragEnd={handleDragEnd}
    >
      <div className="news-item-header">
        <span className="news-item-topic">{item.topic}</span>
        <DragHintIcon />
      </div>
      <a
        className="news-item-title"
        href={item.url}
        target="_blank"
        rel="noopener noreferrer"
        onClick={(e) => e.stopPropagation()}
      >
        {item.title}
      </a>
      <div className="news-item-desc">{item.description}</div>
      <div className="news-item-meta">
        <span className="news-item-source">{item.source}</span>
        <span>{formatNewsTime(item.publishedAt)}</span>
      </div>
    </div>
  );
}

// ─── Main Component ───

export default function NewsPanel() {
  const interests = useNewsStore((s) => s.interests);
  const newsItems = useNewsStore((s) => s.newsItems);
  const loading = useNewsStore((s) => s.loading);
  const refreshing = useNewsStore((s) => s.refreshing);
  const lastUpdated = useNewsStore((s) => s.lastUpdated);
  const initNews = useNewsStore((s) => s.initNews);
  const refreshNews = useNewsStore((s) => s.refreshNews);
  const removeInterest = useNewsStore((s) => s.removeInterest);
  const cleanup = useNewsStore((s) => s.cleanup);

  useEffect(() => {
    initNews();
    return () => {
      cleanup();
    };
  }, [initNews, cleanup]);

  return (
    <div className="news-panel">
      {/* Header */}
      <div className="news-header">
        <span className="news-title">For You</span>
        <button
          className={`news-refresh-btn${refreshing ? ' spinning' : ''}`}
          onClick={() => refreshNews(true)}
          title="Refresh news"
        >
          <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M1 1v5h5" />
            <path d="M3.51 10a5 5 0 1 0 .49-5.5L1 6" />
          </svg>
        </button>
      </div>

      {/* Interests */}
      <div className="news-interests">
        <div className="news-interests-label">Your Interests</div>
        <div className="news-interests-tags">
          {interests.length > 0 ? (
            interests.map((interest) => (
              <span className="news-interest-tag" key={interest}>
                {interest}
                <button
                  className="news-interest-remove"
                  onClick={() => removeInterest(interest)}
                  title={`Remove "${interest}"`}
                >
                  &times;
                </button>
              </span>
            ))
          ) : (
            <span className="news-interest-hint">
              Say &ldquo;我关注...&rdquo; in chat to add interests
            </span>
          )}
        </div>
      </div>

      {/* Last updated */}
      {lastUpdated && (
        <div className="news-updated">
          Updated {lastUpdated.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })}
        </div>
      )}

      {/* News list */}
      <div id="panel-news-list">
        {loading && newsItems.length === 0 ? (
          <div className="news-loading">
            <svg className="spinning" width="20" height="20" viewBox="0 0 16 16" fill="none" stroke="var(--text-tertiary)" strokeWidth="2">
              <circle cx="8" cy="8" r="6" strokeDasharray="28" strokeDashoffset="7" strokeLinecap="round" />
            </svg>
            <div className="news-hint">Fetching personalized news...</div>
          </div>
        ) : newsItems.length === 0 && !loading ? (
          <div className="news-loading">
            <div>No news yet</div>
            <div className="news-hint">Add interests to get personalized news</div>
          </div>
        ) : (
          newsItems.map((item, idx) => (
            <NewsItemCard key={`${item.url}-${idx}`} item={item} />
          ))
        )}
      </div>
    </div>
  );
}
