import { useRef, useState, useCallback, useEffect } from 'react';
import { useDesignStore } from '@/stores/designStore';

interface Stroke {
  points: { x: number; y: number }[];
  color: string;
  width: number;
}

const COLORS = ['#ef4444', '#f59e0b', '#22c55e', '#3b82f6', '#8b5cf6', '#000000'];

export default function DesignDrawOverlay() {
  const interactionMode = useDesignStore((s) => s.interactionMode);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [strokes, setStrokes] = useState<Stroke[]>([]);
  const [currentStroke, setCurrentStroke] = useState<Stroke | null>(null);
  const [color, setColor] = useState('#ef4444');
  const [strokeWidth, setStrokeWidth] = useState(3);
  const drawing = useRef(false);
  const redrawRef = useRef<() => void>(() => {});

  const redraw = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    const allStrokes = currentStroke ? [...strokes, currentStroke] : strokes;
    for (const stroke of allStrokes) {
      if (stroke.points.length < 2) continue;
      ctx.beginPath();
      ctx.strokeStyle = stroke.color;
      ctx.lineWidth = stroke.width;
      ctx.lineCap = 'round';
      ctx.lineJoin = 'round';
      ctx.moveTo(stroke.points[0].x, stroke.points[0].y);
      for (let i = 1; i < stroke.points.length; i++) {
        ctx.lineTo(stroke.points[i].x, stroke.points[i].y);
      }
      ctx.stroke();
    }
  }, [strokes, currentStroke]);

  redrawRef.current = redraw;

  useEffect(() => { redraw(); }, [redraw]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !canvas.parentElement) return;
    const parent = canvas.parentElement;
    const resize = () => {
      const rect = parent.getBoundingClientRect();
      canvas.width = rect.width;
      canvas.height = rect.height;
      redrawRef.current();
    };
    resize();
    const observer = new ResizeObserver(resize);
    observer.observe(parent);
    return () => observer.disconnect();
  }, []);

  const getPos = (e: React.MouseEvent) => {
    const canvas = canvasRef.current;
    if (!canvas) return { x: 0, y: 0 };
    const rect = canvas.getBoundingClientRect();
    return { x: e.clientX - rect.left, y: e.clientY - rect.top };
  };

  const handleMouseDown = (e: React.MouseEvent) => {
    if (interactionMode !== 'draw') return;
    drawing.current = true;
    const pos = getPos(e);
    setCurrentStroke({ points: [pos], color, width: strokeWidth });
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    if (!drawing.current || !currentStroke) return;
    const pos = getPos(e);
    setCurrentStroke({ ...currentStroke, points: [...currentStroke.points, pos] });
  };

  const handleMouseUp = () => {
    if (currentStroke && currentStroke.points.length > 1) {
      setStrokes((prev) => [...prev, currentStroke]);
    }
    setCurrentStroke(null);
    drawing.current = false;
  };

  if (interactionMode !== 'draw' && strokes.length === 0) return null;

  return (
    <div className={`design-draw-overlay${interactionMode === 'draw' ? ' active' : ''}`}>
      <canvas
        ref={canvasRef}
        className="design-draw-canvas"
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}
      />
      {interactionMode === 'draw' && (
        <div className="design-draw-toolbar">
          {COLORS.map((c) => (
            <button
              key={c}
              className={`design-draw-color${color === c ? ' active' : ''}`}
              style={{ background: c }}
              onClick={() => setColor(c)}
            />
          ))}
          <input
            type="range"
            min="1"
            max="10"
            value={strokeWidth}
            onChange={(e) => setStrokeWidth(Number(e.target.value))}
            className="design-draw-size"
            title={`Brush size: ${strokeWidth}px`}
          />
          <button className="design-draw-clear" onClick={() => { setStrokes([]); setCurrentStroke(null); }} title="Clear all">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-2 14H7L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/></svg>
          </button>
        </div>
      )}
    </div>
  );
}
