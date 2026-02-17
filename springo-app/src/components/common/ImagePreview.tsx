import { useEffect, useCallback } from 'react'
import { useUIStore } from '@/stores/uiStore'

/**
 * Fullscreen image preview modal.
 * Shows the image at full size with click-backdrop or Escape to close.
 * Reads from `useUIStore.imagePreview`.
 */
export default function ImagePreview() {
  const imageUrl = useUIStore((s) => s.imagePreview)
  const setImagePreview = useUIStore((s) => s.setImagePreview)

  const close = useCallback(() => setImagePreview(null), [setImagePreview])

  useEffect(() => {
    if (!imageUrl) return
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') close()
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [imageUrl, close])

  if (!imageUrl) return null

  return (
    <div className="image-preview-backdrop" onClick={close}>
      <div className="image-preview-container" onClick={(e) => e.stopPropagation()}>
        <img src={imageUrl} className="image-preview-img" alt="Preview" />
        <button className="image-preview-close" onClick={close} title="Close">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <line x1="18" y1="6" x2="6" y2="18" />
            <line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        </button>
      </div>
    </div>
  )
}
