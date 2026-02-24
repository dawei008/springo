import { useState, useEffect, useRef } from 'react'
import { useUIStore } from '@/stores/uiStore'
import { api } from '@/services/api'
import type { ToolUse } from '@/types'

interface ToolVisualContentProps {
  toolUse: ToolUse
  defaultCollapsed?: boolean
}

function escapeHtml(str: string): string {
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
}

// Collapsible image container with header bar
function CollapsibleVisual({
  label,
  defaultCollapsed = false,
  onOpen,
  children,
}: {
  label: string
  defaultCollapsed?: boolean
  onOpen?: () => void
  children: React.ReactNode
}) {
  const [collapsed, setCollapsed] = useState(defaultCollapsed)

  return (
    <div className={`tool-visual-content${collapsed ? ' collapsed' : ''}`}>
      <div className="tool-visual-header" onClick={() => setCollapsed((c) => !c)}>
        <span className="tool-visual-icon">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
            <circle cx="8.5" cy="8.5" r="1.5" />
            <polyline points="21 15 16 10 5 21" />
          </svg>
        </span>
        <span className="tool-visual-label">{escapeHtml(label)}</span>
        <svg className="tool-visual-toggle" fill="none" stroke="currentColor" viewBox="0 0 24 24" width="14" height="14">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 9l-7 7-7-7" />
        </svg>
        {onOpen && (
          <a
            className="tool-visual-open"
            href="#"
            onClick={(e) => {
              e.preventDefault()
              e.stopPropagation()
              onOpen()
            }}
            title="Open file"
          >
            Open
          </a>
        )}
      </div>
      {!collapsed && <div className="tool-visual-image">{children}</div>}
    </div>
  )
}

/**
 * Detects and renders visual content from tool results.
 * Handles: excalidraw, image URLs, image file paths, base64 images, SVG.
 */
export default function ToolVisualContent({ toolUse, defaultCollapsed = false }: ToolVisualContentProps) {
  const setImagePreview = useUIStore((s) => s.setImagePreview)
  const [imageDataUrls, setImageDataUrls] = useState<Record<string, string>>({})
  const [failedImages, setFailedImages] = useState<Set<string>>(new Set())
  const containerRef = useRef<HTMLDivElement>(null)

  const resultStr = typeof toolUse.result === 'string'
    ? toolUse.result
    : JSON.stringify(toolUse.result || '')

  // --- Excalidraw is handled by ExcalidrawLinkCard in Message.tsx ---

  // --- Image URLs ---
  const imageUrlRegex = /(https?:\/\/[^\s"'`]+\.(?:png|jpg|jpeg|gif|svg|webp)(?:\?[^\s"'`]*)?)/gi
  const imageUrls = resultStr.match(imageUrlRegex)
  if (imageUrls) {
    const unique = [...new Set(imageUrls)]
    if (unique.length > 0) {
      return (
        <>
          {unique.map((url) => {
            const key = `url-${toolUse.id}-${url.replace(/[^a-zA-Z0-9]/g, '_').slice(0, 80)}`
            const fileName = url.split('/').pop()?.split('?')[0] || 'image'
            return (
              <CollapsibleVisual key={key} label={fileName} defaultCollapsed={defaultCollapsed}>
                <img
                  src={url}
                  className="tool-visual-inline-image"
                  alt="Tool output"
                  onClick={() => setImagePreview(url)}
                  onError={(e) => {
                    ;(e.target as HTMLElement).parentElement!.style.display = 'none'
                  }}
                />
              </CollapsibleVisual>
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
    if (paths.length > 0) {
      return (
        <>
          {paths.map((filePath) => {
            const key = `img-${toolUse.id}-${filePath.replace(/[^a-zA-Z0-9]/g, '_')}`
            const fileName = filePath.split('/').pop() || filePath
            return (
              <CollapsibleVisual
                key={key}
                label={fileName}
                defaultCollapsed={defaultCollapsed}
                onOpen={() => window.electronAPI?.openPath(filePath)}
              >
                <div ref={containerRef}>
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
              </CollapsibleVisual>
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
    return (
      <CollapsibleVisual label="Generated Image" defaultCollapsed={defaultCollapsed}>
        <img
          src={base64Match[0]}
          className="tool-visual-inline-image"
          alt="Tool output"
          onClick={() => setImagePreview(base64Match[0])}
        />
      </CollapsibleVisual>
    )
  }

  // --- SVG content ---
  if (resultStr.includes('<svg') && resultStr.includes('</svg>')) {
    const svgMatch = resultStr.match(/<svg[\s\S]*?<\/svg>/i)
    if (svgMatch) {
      return (
        <CollapsibleVisual label="SVG Diagram" defaultCollapsed={defaultCollapsed}>
          <div
            className="tool-visual-svg-inner"
            dangerouslySetInnerHTML={{ __html: svgMatch[0] }}
          />
        </CollapsibleVisual>
      )
    }
  }

  return null
}
