import { useRef, useEffect, useState, useMemo } from 'react'

interface Artifact {
  id: string
  title: string
  html: string
}

/** Model-generated artifact via <springo-artifact> tags */
export interface ModelArtifact {
  id: string
  type: 'markdown' | 'html' | 'svg' | 'code'
  title: string
  content: string
}

interface ArtifactRendererProps {
  /** Raw markdown/text content that may contain HTML artifacts. */
  text: string
  /** Callback providing cleaned text (artifacts replaced with placeholders) and extracted artifacts. */
  children: (cleaned: string, artifacts: Artifact[]) => React.ReactNode
}

/** Internal store for artifact HTML keyed by id (dedup across streaming re-renders). */
const artifactStore: Record<string, string> = {}
let artifactCounter = 0

function isFullHtmlDocument(code: string): boolean {
  const lower = code.trim().toLowerCase()
  return (lower.includes('<!doctype html') || lower.includes('<html')) && lower.includes('</html>')
}

function escapeHtml(str: string): string {
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
}

/** Map springo-artifact type attr to internal type */
function mapArtifactType(typeAttr: string): ModelArtifact['type'] {
  if (typeAttr === 'design/project') return 'html'  // multi-file project treated as html for card display
  if (typeAttr.includes('html')) return 'html'
  if (typeAttr.includes('svg')) return 'svg'
  if (typeAttr.includes('code')) return 'code'
  return 'markdown'
}

let modelArtifactCounter = 0

import type { DesignFile, DesignFileType } from '@/types'

/**
 * Parse <springo-file> tags from within a design/project artifact.
 */
export function parseSpringoFiles(content: string): DesignFile[] {
  const files: DesignFile[] = []
  const re = /<springo-file\s+([^>]*?)>([\s\S]*?)<\/springo-file>/g
  let m: RegExpExecArray | null
  while ((m = re.exec(content)) !== null) {
    const attrs = m[1]
    const body = m[2]
    const pathMatch = attrs.match(/path="([^"]*)"/)
    const typeMatch = attrs.match(/type="([^"]*)"/)
    const path = pathMatch?.[1] || `file-${files.length}`
    const rawType = typeMatch?.[1] || ''
    let fileType: DesignFileType = 'text'
    if (rawType.includes('jsx') || path.endsWith('.jsx') || path.endsWith('.tsx')) fileType = 'jsx'
    else if (rawType.includes('css') || path.endsWith('.css')) fileType = 'css'
    else if (rawType.includes('html') || path.endsWith('.html')) fileType = 'html'
    else if (rawType.includes('json') || path.endsWith('.json')) fileType = 'json'
    files.push({ path, type: fileType, content: body.trim() })
  }
  return files
}

/**
 * Extract <springo-artifact> tags from model output.
 * Returns cleaned text (tags replaced) and extracted artifacts.
 */
export function extractModelArtifacts(text: string): { cleaned: string; artifacts: ModelArtifact[] } {
  if (!text || typeof text !== 'string') return { cleaned: text, artifacts: [] }

  const artifacts: ModelArtifact[] = []
  let cleaned = text.replace(
    /<springo-artifact\s+([^>]*?)>([\s\S]*?)<\/springo-artifact>/g,
    (_match, attrs: string, content: string) => {
      const typeMatch = attrs.match(/type="([^"]*)"/)
      const titleMatch = attrs.match(/title="([^"]*)"/)
      const idMatch = attrs.match(/id="([^"]*)"/)
      const rawType = typeMatch?.[1] || 'text/markdown'
      const type = mapArtifactType(rawType)
      const title = titleMatch?.[1] || 'Artifact'
      const id = idMatch?.[1] || `mart-${++modelArtifactCounter}`
      artifacts.push({
        id, type, title, content: content.trim(),
        _isProject: rawType === 'design/project',
      } as ModelArtifact & { _isProject?: boolean })
      return '' // Remove from inline text
    }
  )

  // During streaming, the closing tag may not have arrived yet.
  // Strip incomplete artifact content to prevent raw code from showing in chat.
  const incompleteIdx = cleaned.indexOf('<springo-artifact')
  if (incompleteIdx !== -1) {
    cleaned = cleaned.substring(0, incompleteIdx)
  }

  return { cleaned: cleaned.trim(), artifacts }
}

/**
 * Extract HTML artifacts from text before markdown rendering.
 * Returns cleaned text plus an array of artifact metadata.
 */
export function extractHtmlArtifacts(text: string): { cleaned: string; artifacts: Artifact[] } {
  if (!text || typeof text !== 'string') return { cleaned: text, artifacts: [] }

  const artifacts: Artifact[] = []

  let result = text

  // Pattern 1: ```html ... ``` code fence with full HTML doc
  result = result.replace(/```html\s*\n([\s\S]*?)\n```/g, (match, code: string) => {
    if (!isFullHtmlDocument(code)) return match
    return createPlaceholder(code.trim(), artifacts)
  })

  // Pattern 2: Raw <!DOCTYPE html>...</html>
  result = result.replace(/(<!DOCTYPE\s+html[^>]*>[\s\S]*?<\/html>)/gi, (match) => {
    return createPlaceholder(match.trim(), artifacts)
  })

  // Pattern 3: <html>...</html> without doctype (only if we didn't already replace)
  if (!result.includes('artifact-container')) {
    result = result.replace(/(<html[\s>][\s\S]*?<\/html>)/gi, (match) => {
      return createPlaceholder(match.trim(), artifacts)
    })
  }

  return { cleaned: result, artifacts }
}

function createPlaceholder(htmlSource: string, artifacts: Artifact[]): string {
  // Dedup: reuse ID if same HTML already stored
  let id = Object.keys(artifactStore).find((k) => artifactStore[k] === htmlSource)
  if (!id) {
    id = `artifact-${++artifactCounter}`
    artifactStore[id] = htmlSource
  }

  const titleMatch = htmlSource.match(/<title[^>]*>([\s\S]*?)<\/title>/i)
  const title = titleMatch ? titleMatch[1].trim() : 'HTML Artifact'

  artifacts.push({ id, title, html: htmlSource })

  // Return a marker div that survives markdown parsing
  return `\n\n<div class="artifact-container" data-artifact-id="${id}"></div>\n\n`
}

// ------------------------------------------------------------------
// ArtifactIframe: sandboxed iframe for a single artifact
// ------------------------------------------------------------------

function ArtifactIframe({ artifact }: { artifact: Artifact }) {
  const iframeRef = useRef<HTMLIFrameElement>(null)
  const [height, setHeight] = useState(400)

  useEffect(() => {
    const iframe = iframeRef.current
    if (!iframe) return
    iframe.srcdoc = artifact.html

    const onLoad = () => {
      try {
        const doc = iframe.contentDocument || iframe.contentWindow?.document
        if (doc) {
          const h = doc.documentElement.scrollHeight
          if (h > 0) setHeight(Math.min(h + 20, 800))
          const observer = new ResizeObserver(() => {
            const nh = doc.documentElement.scrollHeight
            if (nh > 0) setHeight(Math.min(nh + 20, 800))
          })
          observer.observe(doc.documentElement)
          return () => observer.disconnect()
        }
      } catch {
        setHeight(500)
      }
    }

    iframe.addEventListener('load', onLoad)
    return () => iframe.removeEventListener('load', onLoad)
  }, [artifact.html])

  function openInNewWindow() {
    if (window.electronAPI?.openArtifactWindow) {
      window.electronAPI.openArtifactWindow(artifact.html, artifact.title)
    } else {
      const win = window.open('', '_blank', 'width=1024,height=768')
      if (win) {
        win.document.open()
        win.document.write(artifact.html)
        win.document.close()
      }
    }
  }

  return (
    <div className="artifact-container">
      <div className="artifact-header">
        <span className="artifact-icon">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M13 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z" />
            <polyline points="13 2 13 9 20 9" />
          </svg>
        </span>
        <span className="artifact-title">{escapeHtml(artifact.title)}</span>
        <button className="artifact-open-btn" onClick={openInNewWindow} title="Open in new window">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
            <polyline points="15 3 21 3 21 9" />
            <line x1="10" y1="14" x2="21" y2="3" />
          </svg>
        </button>
      </div>
      <div className="artifact-iframe-wrapper">
        <iframe
          ref={iframeRef}
          className="artifact-iframe"
          sandbox="allow-scripts allow-same-origin"
          loading="lazy"
          style={{ height }}
        />
      </div>
    </div>
  )
}

// ------------------------------------------------------------------
// ArtifactRenderer: wraps content and renders embedded artifacts
// ------------------------------------------------------------------

/**
 * Renders HTML artifacts found in message text.
 * Use as a render-prop component:
 *
 * ```tsx
 * <ArtifactRenderer text={messageText}>
 *   {(cleanedText, artifacts) => (
 *     <>
 *       <div dangerouslySetInnerHTML={{ __html: parseMarkdown(cleanedText) }} />
 *       {artifacts.map(a => <ArtifactIframe key={a.id} artifact={a} />)}
 *     </>
 *   )}
 * </ArtifactRenderer>
 * ```
 */
export default function ArtifactRenderer({ text, children }: ArtifactRendererProps) {
  const { cleaned, artifacts } = useMemo(() => extractHtmlArtifacts(text), [text])
  return <>{children(cleaned, artifacts)}</>
}

/** Standalone component to render a single artifact by id (for post-render activation). */
export function ArtifactInline({ artifactId }: { artifactId: string }) {
  const html = artifactStore[artifactId]
  if (!html) return null

  const titleMatch = html.match(/<title[^>]*>([\s\S]*?)<\/title>/i)
  const title = titleMatch ? titleMatch[1].trim() : 'HTML Artifact'

  return <ArtifactIframe artifact={{ id: artifactId, title, html }} />
}

/**
 * Activate artifact placeholders within a DOM container.
 * Scans for `.artifact-container[data-artifact-id]` and renders iframes.
 * This is a compatibility helper for imperative DOM insertion;
 * prefer using `<ArtifactRenderer>` or `<ArtifactInline>` in React code.
 */
export function activateArtifactsInContainer(container: HTMLElement) {
  if (!container) return
  container.querySelectorAll<HTMLIFrameElement>('iframe.artifact-iframe').forEach((iframe) => {
    const id = iframe.getAttribute('data-artifact-id')
    if (!id || !artifactStore[id]) return
    if (iframe.getAttribute('srcdoc')) return
    iframe.srcdoc = artifactStore[id]
    iframe.onload = () => {
      try {
        const doc = iframe.contentDocument || iframe.contentWindow?.document
        if (doc) {
          const h = doc.documentElement.scrollHeight
          if (h > 0) iframe.style.height = Math.min(h + 20, 800) + 'px'
        }
      } catch {
        iframe.style.height = '500px'
      }
    }
  })
}
