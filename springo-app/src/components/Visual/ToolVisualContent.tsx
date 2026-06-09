import { useState, useEffect, useRef, useMemo } from 'react'
import { useUIStore } from '@/stores/uiStore'
import { api } from '@/services/api'
import type { ToolUse } from '@/types'
import { escapeHtml } from '@/utils/escapeHtml'

interface ToolVisualContentProps {
  toolUse: ToolUse
  defaultCollapsed?: boolean
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
 * Extract MCP-format image content blocks from the tool result object.
 * MCP tools return: {content: [{type: "image", mimeType: "image/png", data: "base64..."}]}
 */
function extractMcpImages(result: unknown): Array<{ mimeType: string; data: string }> {
  if (!result || typeof result !== 'object') return []
  const obj = result as Record<string, unknown>
  const content = obj.content
  if (!Array.isArray(content)) return []
  const images: Array<{ mimeType: string; data: string }> = []
  for (const block of content) {
    if (
      block &&
      typeof block === 'object' &&
      (block as Record<string, unknown>).type === 'image'
    ) {
      const b = block as Record<string, unknown>
      const data = (b.data as string) || ''
      const mimeType = (b.mimeType as string) || 'image/png'
      if (data.length > 50) {
        images.push({ mimeType, data })
      }
    }
  }
  return images
}

/**
 * Detects and renders visual content from tool results.
 * Priority: MCP image blocks > data URLs > HTTP URLs > local file paths > SVG.
 */
export default function ToolVisualContent({ toolUse, defaultCollapsed = false }: ToolVisualContentProps) {
  const setImagePreview = useUIStore((s) => s.setImagePreview)
  const [imageDataUrls, setImageDataUrls] = useState<Record<string, string>>({})
  const [failedImages, setFailedImages] = useState<Set<string>>(new Set())
  const containerRef = useRef<HTMLDivElement>(null)

  // Memoize all parsing: tool results don't change after the tool completes,
  // but the parent re-renders this on every streaming token of the active turn.
  const detected = useMemo(() => {
    const resultStr = typeof toolUse.result === 'string'
      ? toolUse.result
      : JSON.stringify(toolUse.result || '')
    const mcpImages = extractMcpImages(toolUse.result)
    const base64Match = resultStr.match(/data:(image\/[a-z+]+);base64,([A-Za-z0-9+/=]{50,})/)
    const imageUrls = resultStr.match(/(https?:\/\/[^\s"'`]+\.(?:png|jpg|jpeg|gif|svg|webp)(?:\?[^\s"'`]*)?)/gi)
    const imagePaths = resultStr.match(/(?<!\w)(\/(?!\.\.)[^\s"'`,]+\.(?:png|jpg|jpeg|gif|svg|webp|bmp))/gi)
    const svgMatch = resultStr.includes('<svg') && resultStr.includes('</svg>')
      ? resultStr.match(/<svg[\s\S]*?<\/svg>/i)
      : null
    return { resultStr, mcpImages, base64Match, imageUrls, imagePaths, svgMatch }
  }, [toolUse.result])

  const { mcpImages, base64Match, imageUrls, imagePaths, svgMatch } = detected

  // Fetch any local image paths from the backend.
  // Hooks must run unconditionally — keep this above the early returns.
  useEffect(() => {
    if (!imagePaths) return
    const paths = [...new Set(imagePaths)].map((p) => p.replace(/["'\\]+$/g, '').trim())
    // One controller per fetch so a single path's timeout can't cancel the
    // others; we track them all to abort any in-flight request on cleanup.
    const controllers = new Set<AbortController>()
    let cancelled = false
    paths.forEach(async (filePath) => {
      if (imageDataUrls[filePath] || failedImages.has(filePath)) return
      const controller = new AbortController()
      controllers.add(controller)
      const timer = setTimeout(() => controller.abort(), 8000)
      try {
        const baseUrl = api.getBaseUrl()
        const res = await fetch(
          `${baseUrl}/v1/images/file?path=${encodeURIComponent(filePath)}`,
          { signal: controller.signal },
        )
        // Bail out if the effect was cleaned up (stale re-run) while awaiting.
        if (cancelled) return
        if (res.ok) {
          const blob = await res.blob()
          if (cancelled) return
          const url = URL.createObjectURL(blob)
          setImageDataUrls((prev) => ({ ...prev, [filePath]: url }))
        } else {
          setFailedImages((prev) => new Set(prev).add(filePath))
        }
      } catch (err) {
        // Ignore aborts (stale effect re-run or timeout); only record real failures.
        if (cancelled || (err instanceof DOMException && err.name === 'AbortError')) return
        setFailedImages((prev) => new Set(prev).add(filePath))
      } finally {
        clearTimeout(timer)
        controllers.delete(controller)
      }
    })
    // imageDataUrls/failedImages intentionally omitted: we only want to fetch
    // when the detected paths change, not on each cache update.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    return () => {
      cancelled = true
      controllers.forEach((c) => c.abort())
    }
  }, [imagePaths])

  // --- MCP image content blocks (highest priority — inline base64, always works) ---
  if (mcpImages.length > 0) {
    return (
      <>
        {mcpImages.map((img, i) => {
          const dataUrl = `data:${img.mimeType};base64,${img.data}`
          const label = mcpImages.length === 1 ? 'Screenshot' : `Image ${i + 1}`
          return (
            <CollapsibleVisual key={`mcp-${toolUse.id}-${i}`} label={label} defaultCollapsed={defaultCollapsed}>
              <img
                src={dataUrl}
                className="tool-visual-inline-image"
                alt={label}
                onClick={() => setImagePreview(dataUrl)}
              />
            </CollapsibleVisual>
          )
        })}
      </>
    )
  }

  // --- Data URL base64 images (e.g. data:image/png;base64,...) ---
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

  // --- Image URLs ---
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

  // --- Image file paths (absolute paths only, fetch from backend) ---
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

  // --- SVG content ---
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

  return null
}
