import { useState, useEffect, useRef } from 'react'
import { useUIStore } from '@/stores/uiStore'
import { api } from '@/services/api'
import ExcalidrawPreview from './ExcalidrawPreview'
import type { ToolUse } from '@/types'

interface ToolVisualContentProps {
  toolUse: ToolUse
}

/** Set of visual-ids already rendered (deduplication across re-renders). */
const renderedVisuals = new Set<string>()

/** Reset dedup set (call when switching sessions). */
export function resetVisualDedup() {
  renderedVisuals.clear()
}

function escapeHtml(str: string): string {
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
}

/**
 * Detects and renders visual content from tool results.
 * Handles: excalidraw, image URLs, image file paths, base64 images, SVG.
 */
export default function ToolVisualContent({ toolUse }: ToolVisualContentProps) {
  const setImagePreview = useUIStore((s) => s.setImagePreview)
  const [imageDataUrls, setImageDataUrls] = useState<Record<string, string>>({})
  const [failedImages, setFailedImages] = useState<Set<string>>(new Set())
  const containerRef = useRef<HTMLDivElement>(null)

  const resultStr = typeof toolUse.result === 'string'
    ? toolUse.result
    : JSON.stringify(toolUse.result || '')

  // --- Excalidraw ---
  if (toolUse.name === 'excalidraw__create_view' && toolUse.input?.elements) {
    const dedupKey = `excalidraw-${toolUse.id}`
    if (renderedVisuals.has(dedupKey)) return null
    renderedVisuals.add(dedupKey)
    return (
      <div className="tool-visual-content" data-visual-id={dedupKey}>
        <ExcalidrawPreview elements={toolUse.input.elements as unknown[]} />
      </div>
    )
  }

  // --- Image URLs ---
  const imageUrlRegex = /(https?:\/\/[^\s"'`]+\.(?:png|jpg|jpeg|gif|svg|webp)(?:\?[^\s"'`]*)?)/gi
  const imageUrls = resultStr.match(imageUrlRegex)
  if (imageUrls) {
    const unique = [...new Set(imageUrls)]
    const visuals = unique.filter((url) => {
      const key = `url-${toolUse.id}-${url.replace(/[^a-zA-Z0-9]/g, '_').slice(0, 80)}`
      if (renderedVisuals.has(key)) return false
      renderedVisuals.add(key)
      return true
    })
    if (visuals.length > 0) {
      return (
        <>
          {visuals.map((url) => {
            const key = `url-${toolUse.id}-${url.replace(/[^a-zA-Z0-9]/g, '_').slice(0, 80)}`
            return (
              <div key={key} className="tool-visual-content" data-visual-id={key}>
                <img
                  src={url}
                  className="tool-visual-inline-image"
                  alt="Tool output"
                  onClick={() => setImagePreview(url)}
                  onError={(e) => {
                    ;(e.target as HTMLElement).parentElement!.style.display = 'none'
                  }}
                />
              </div>
            )
          })}
        </>
      )
    }
  }

  // --- Image file paths ---
  const imagePathRegex = /(?<!\w)(\/[^\s"'`,]+\.(?:png|jpg|jpeg|gif|svg|webp|bmp))/gi
  const imagePaths = resultStr.match(imagePathRegex)

  useEffect(() => {
    if (!imagePaths) return
    const paths = [...new Set(imagePaths)].map((p) => p.replace(/["'\\]+$/g, '').trim())
    paths.forEach(async (filePath) => {
      if (imageDataUrls[filePath] || failedImages.has(filePath)) return
      try {
        const baseUrl = api.getBaseUrl()
        const res = await fetch(`${baseUrl}/v1/images/file?path=${encodeURIComponent(filePath)}`)
        if (res.ok) {
          const blob = await res.blob()
          const url = URL.createObjectURL(blob)
          setImageDataUrls((prev) => ({ ...prev, [filePath]: url }))
        } else {
          setFailedImages((prev) => new Set(prev).add(filePath))
        }
      } catch {
        setFailedImages((prev) => new Set(prev).add(filePath))
      }
    })
  }, [resultStr])

  if (imagePaths) {
    const paths = [...new Set(imagePaths)].map((p) => p.replace(/["'\\]+$/g, '').trim())
    const visuals = paths.filter((p) => {
      const key = `img-${toolUse.id}-${p.replace(/[^a-zA-Z0-9]/g, '_')}`
      if (renderedVisuals.has(key)) return false
      renderedVisuals.add(key)
      return true
    })
    if (visuals.length > 0) {
      return (
        <>
          {visuals.map((filePath) => {
            const key = `img-${toolUse.id}-${filePath.replace(/[^a-zA-Z0-9]/g, '_')}`
            const fileName = filePath.split('/').pop() || filePath
            return (
              <div key={key} className="tool-visual-content" data-visual-id={key} ref={containerRef}>
                <div className="tool-visual-header">
                  <span className="tool-visual-icon">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
                      <circle cx="8.5" cy="8.5" r="1.5" />
                      <polyline points="21 15 16 10 5 21" />
                    </svg>
                  </span>
                  <span className="tool-visual-label">{escapeHtml(fileName)}</span>
                  <a
                    className="tool-visual-open"
                    href="#"
                    onClick={(e) => {
                      e.preventDefault()
                      window.electronAPI?.openPath(filePath)
                    }}
                    title="Open file"
                  >
                    Open
                  </a>
                </div>
                <div className="tool-visual-image">
                  {imageDataUrls[filePath] ? (
                    <img
                      src={imageDataUrls[filePath]}
                      className="tool-visual-inline-image"
                      alt={fileName}
                      onClick={() => setImagePreview(imageDataUrls[filePath])}
                    />
                  ) : failedImages.has(filePath) ? (
                    <span className="tool-visual-error">Image not found</span>
                  ) : (
                    <span className="tool-visual-loading">Loading...</span>
                  )}
                </div>
              </div>
            )
          })}
        </>
      )
    }
  }

  // --- Base64 images ---
  const base64Regex = /data:(image\/[a-z+]+);base64,([A-Za-z0-9+/=]{50,})/
  const base64Match = resultStr.match(base64Regex)
  if (base64Match) {
    const dedupKey = `b64-${toolUse.id}`
    if (!renderedVisuals.has(dedupKey)) {
      renderedVisuals.add(dedupKey)
      return (
        <div className="tool-visual-content" data-visual-id={dedupKey}>
          <img
            src={base64Match[0]}
            className="tool-visual-inline-image"
            alt="Tool output"
            onClick={() => setImagePreview(base64Match[0])}
          />
        </div>
      )
    }
  }

  // --- SVG content ---
  if (resultStr.includes('<svg') && resultStr.includes('</svg>')) {
    const svgMatch = resultStr.match(/<svg[\s\S]*?<\/svg>/i)
    if (svgMatch) {
      const dedupKey = `svg-${toolUse.id}`
      if (!renderedVisuals.has(dedupKey)) {
        renderedVisuals.add(dedupKey)
        return (
          <div
            className="tool-visual-content tool-visual-svg"
            data-visual-id={dedupKey}
            dangerouslySetInnerHTML={{ __html: svgMatch[0] }}
          />
        )
      }
    }
  }

  return null
}
