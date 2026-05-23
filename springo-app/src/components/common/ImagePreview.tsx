import { useEffect, useCallback, useState, useRef } from 'react'
import { useUIStore } from '@/stores/uiStore'

/**
 * Fullscreen image preview modal.
 *
 * - Defaults to "fit" — image scales to fill viewport up to its natural size,
 *   so big files (3000+px posters) actually become visible instead of
 *   overflowing.
 * - Wheel / pinch / +/- keys zoom around the cursor.
 * - Drag to pan when zoomed > fit.
 * - Double-click toggles between fit and 100% (1:1 native).
 * - 0 key resets to fit; Esc closes.
 */
export default function ImagePreview() {
  const imageUrl = useUIStore((s) => s.imagePreview)
  const setImagePreview = useUIStore((s) => s.setImagePreview)

  const [scale, setScale] = useState(1)
  const [tx, setTx] = useState(0)
  const [ty, setTy] = useState(0)
  const [naturalSize, setNaturalSize] = useState<{ w: number; h: number } | null>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const dragRef = useRef<{ startX: number; startY: number; startTx: number; startTy: number } | null>(null)

  const close = useCallback(() => setImagePreview(null), [setImagePreview])

  // Reset transforms whenever a new image opens.
  useEffect(() => {
    setScale(1)
    setTx(0)
    setTy(0)
    setNaturalSize(null)
  }, [imageUrl])

  // Compute the "fit" scale: largest multiplier that keeps the image inside
  // the viewport. < 1 means we're shrinking the natural image; > 1 means
  // viewport is bigger than the image and we leave it 1:1 by capping.
  const fitScale = (() => {
    if (!naturalSize) return 1
    const margin = 64 // breathing room around the edges
    const vw = window.innerWidth - margin
    const vh = window.innerHeight - margin
    return Math.min(vw / naturalSize.w, vh / naturalSize.h, 1)
  })()

  const reset = useCallback(() => {
    setScale(1)
    setTx(0)
    setTy(0)
  }, [])

  const toggleFitNative = useCallback(() => {
    // scale of `1` in our state means "render at fit", we apply fitScale on
    // top via CSS — so toggling means swap state.scale between 1 and 1/fitScale.
    setScale((s) => (Math.abs(s - 1) < 0.001 ? 1 / Math.max(fitScale, 0.0001) : 1))
    setTx(0)
    setTy(0)
  }, [fitScale])

  // Keyboard.
  useEffect(() => {
    if (!imageUrl) return
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') { close(); return }
      if (e.key === '0') { reset(); return }
      if (e.key === '+' || e.key === '=') { setScale((s) => Math.min(s * 1.25, 16)); return }
      if (e.key === '-' || e.key === '_') { setScale((s) => Math.max(s / 1.25, 0.1)); return }
      if (e.key === '1') { toggleFitNative(); return }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [imageUrl, close, reset, toggleFitNative])

  // Wheel zoom around cursor position (Ctrl/Cmd not required — direct scroll
  // zooms because users expect that in image viewers).
  const onWheel = useCallback((e: React.WheelEvent) => {
    e.preventDefault()
    const factor = e.deltaY < 0 ? 1.1 : 1 / 1.1
    const container = containerRef.current
    if (!container) {
      setScale((s) => Math.max(0.1, Math.min(16, s * factor)))
      return
    }
    const rect = container.getBoundingClientRect()
    const cx = e.clientX - rect.left - rect.width / 2
    const cy = e.clientY - rect.top - rect.height / 2

    setScale((prev) => {
      const next = Math.max(0.1, Math.min(16, prev * factor))
      const ratio = next / prev
      // Adjust pan so the point under the cursor stays under the cursor.
      setTx((t) => cx - (cx - t) * ratio)
      setTy((t) => cy - (cy - t) * ratio)
      return next
    })
  }, [])

  // Drag to pan.
  const onMouseDown = useCallback((e: React.MouseEvent) => {
    if (e.button !== 0) return
    dragRef.current = {
      startX: e.clientX,
      startY: e.clientY,
      startTx: tx,
      startTy: ty,
    }
  }, [tx, ty])

  useEffect(() => {
    function onMove(e: MouseEvent) {
      const d = dragRef.current
      if (!d) return
      setTx(d.startTx + (e.clientX - d.startX))
      setTy(d.startTy + (e.clientY - d.startY))
    }
    function onUp() { dragRef.current = null }
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
    return () => {
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
    }
  }, [])

  if (!imageUrl) return null

  // Final scale = fit-to-viewport baseline × user zoom. fitScale is computed
  // from naturalSize; before that we render at 1 with visibility hidden so
  // the user never sees a flash of the gigantic raw image.
  const effectiveScale = fitScale * scale
  const ready = !!naturalSize

  return (
    <div className="image-preview-backdrop" onClick={close} ref={containerRef} onWheel={onWheel}>
      <div
        className="image-preview-stage"
        onClick={(e) => e.stopPropagation()}
        onMouseDown={onMouseDown}
        onDoubleClick={toggleFitNative}
        style={{
          cursor: dragRef.current ? 'grabbing' : (effectiveScale > fitScale ? 'grab' : 'zoom-in'),
        }}
      >
        <img
          src={imageUrl}
          alt="Preview"
          className="image-preview-img"
          draggable={false}
          onLoad={(e) => {
            const img = e.currentTarget
            setNaturalSize({ w: img.naturalWidth, h: img.naturalHeight })
          }}
          style={{
            transform: `translate(${tx}px, ${ty}px) scale(${effectiveScale})`,
            visibility: ready ? 'visible' : 'hidden',
          }}
        />
      </div>

      <div className="image-preview-toolbar" onClick={(e) => e.stopPropagation()}>
        <button onClick={() => setScale((s) => Math.max(s / 1.25, 0.1))} title="Zoom out (-)">−</button>
        <span className="image-preview-zoom-label">{Math.round(effectiveScale * 100)}%</span>
        <button onClick={() => setScale((s) => Math.min(s * 1.25, 16))} title="Zoom in (+)">+</button>
        <button onClick={reset} title="Fit to screen (0)">Fit</button>
        <button onClick={toggleFitNative} title="Toggle 100% (1)">1:1</button>
      </div>

      <button className="image-preview-close" onClick={close} title="Close (Esc)">
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <line x1="18" y1="6" x2="6" y2="18" />
          <line x1="6" y1="6" x2="18" y2="18" />
        </svg>
      </button>
    </div>
  )
}
