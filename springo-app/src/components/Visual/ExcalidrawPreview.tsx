import { useMemo } from 'react'

interface ExcalidrawElement {
  id?: string
  type: string
  x?: number
  y?: number
  width?: number
  height?: number
  strokeColor?: string
  backgroundColor?: string
  strokeWidth?: number
  opacity?: number
  roundness?: unknown
  text?: string
  fontSize?: number
  textAlign?: string
  points?: number[][]
  [key: string]: unknown
}

interface ExcalidrawPreviewProps {
  elements: unknown[]
  onOpen?: () => void
}

function escapeHtml(str: string): string {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

/**
 * Pure SVG renderer for Excalidraw JSON elements.
 * Converts elements to inline SVG shapes with proper viewBox.
 */
export default function ExcalidrawPreview({ elements: rawElements, onOpen }: ExcalidrawPreviewProps) {
  const svgContent = useMemo(() => {
    try {
      const parsed: ExcalidrawElement[] =
        typeof rawElements === 'string' ? JSON.parse(rawElements as string) : rawElements
      if (!Array.isArray(parsed)) return null

      const renderable = parsed.filter(
        (el) => el.type && !['cameraUpdate'].includes(el.type),
      ) as ExcalidrawElement[]
      if (renderable.length === 0) return null

      // Bounding box
      let minX = Infinity
      let minY = Infinity
      let maxX = -Infinity
      let maxY = -Infinity

      for (const el of renderable) {
        const x = el.x || 0
        const y = el.y || 0
        const w = el.width || (el.text ? el.text.length * (el.fontSize || 16) * 0.6 : 0)
        const h = el.height || (el.text ? el.text.split('\n').length * (el.fontSize || 16) * 1.3 : 0)
        minX = Math.min(minX, x)
        minY = Math.min(minY, y)
        maxX = Math.max(maxX, x + w)
        maxY = Math.max(maxY, y + h)
        if (el.points) {
          for (const p of el.points) {
            minX = Math.min(minX, x + (p[0] || 0))
            minY = Math.min(minY, y + (p[1] || 0))
            maxX = Math.max(maxX, x + (p[0] || 0))
            maxY = Math.max(maxY, y + (p[1] || 0))
          }
        }
      }

      const pad = 30
      minX -= pad
      minY -= pad
      maxX += pad
      maxY += pad
      const vw = maxX - minX
      const vh = maxY - minY

      // Render elements
      const svgParts: string[] = []
      for (const el of renderable) {
        const stroke = el.strokeColor || '#1e1e1e'
        const fill =
          el.backgroundColor && el.backgroundColor !== 'transparent'
            ? el.backgroundColor
            : 'none'
        const sw = el.strokeWidth || 1
        const opacity = el.opacity != null ? el.opacity / 100 : 1
        const x = el.x || 0
        const y = el.y || 0

        switch (el.type) {
          case 'rectangle': {
            const w = el.width || 0
            const h = el.height || 0
            const rx = el.roundness ? Math.min(w, h) * 0.1 : 0
            svgParts.push(
              `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="${rx}" ` +
                `stroke="${escapeHtml(stroke)}" fill="${escapeHtml(fill)}" stroke-width="${sw}" opacity="${opacity}"/>`,
            )
            break
          }
          case 'diamond': {
            const w = el.width || 0
            const h = el.height || 0
            const cx = x + w / 2
            const cy = y + h / 2
            const pts = `${cx},${y} ${x + w},${cy} ${cx},${y + h} ${x},${cy}`
            svgParts.push(
              `<polygon points="${pts}" stroke="${escapeHtml(stroke)}" fill="${escapeHtml(fill)}" ` +
                `stroke-width="${sw}" opacity="${opacity}"/>`,
            )
            break
          }
          case 'ellipse': {
            const rx = (el.width || 0) / 2
            const ry = (el.height || 0) / 2
            svgParts.push(
              `<ellipse cx="${x + rx}" cy="${y + ry}" rx="${rx}" ry="${ry}" ` +
                `stroke="${escapeHtml(stroke)}" fill="${escapeHtml(fill)}" stroke-width="${sw}" opacity="${opacity}"/>`,
            )
            break
          }
          case 'text': {
            const fs = el.fontSize || 16
            const lines = (el.text || '').split('\n')
            const anchor =
              el.textAlign === 'center' ? 'middle' : el.textAlign === 'right' ? 'end' : 'start'
            const tx = el.textAlign === 'center' ? x + (el.width || 0) / 2 : x
            for (let li = 0; li < lines.length; li++) {
              const ty = y + fs * 0.85 + li * fs * 1.3
              svgParts.push(
                `<text x="${tx}" y="${ty}" font-size="${fs}" fill="${escapeHtml(stroke)}" ` +
                  `font-family="'Segoe UI', system-ui, sans-serif" text-anchor="${anchor}" opacity="${opacity}">` +
                  `${escapeHtml(lines[li])}</text>`,
              )
            }
            break
          }
          case 'arrow':
          case 'line': {
            if (el.points && el.points.length >= 2) {
              const pts = el.points.map((p) => `${x + (p[0] || 0)},${y + (p[1] || 0)}`).join(' ')
              const markerId =
                el.type === 'arrow'
                  ? `arrow-${el.id || Math.random().toString(36).slice(2)}`
                  : ''
              if (markerId) {
                svgParts.push(
                  `<defs><marker id="${markerId}" viewBox="0 0 10 10" refX="9" refY="5" ` +
                    `markerWidth="6" markerHeight="6" orient="auto-start-reverse">` +
                    `<path d="M 0 0 L 10 5 L 0 10 z" fill="${escapeHtml(stroke)}"/></marker></defs>`,
                )
              }
              svgParts.push(
                `<polyline points="${pts}" stroke="${escapeHtml(stroke)}" fill="none" ` +
                  `stroke-width="${sw}" opacity="${opacity}"` +
                  (markerId ? ` marker-end="url(#${markerId})"` : '') +
                  `/>`,
              )
            }
            break
          }
          case 'freedraw': {
            if (el.points && el.points.length >= 2) {
              let d = `M ${x + el.points[0][0]} ${y + el.points[0][1]}`
              for (let i = 1; i < el.points.length; i++) {
                d += ` L ${x + el.points[i][0]} ${y + el.points[i][1]}`
              }
              svgParts.push(
                `<path d="${d}" stroke="${escapeHtml(stroke)}" fill="none" ` +
                  `stroke-width="${sw}" opacity="${opacity}" stroke-linecap="round"/>`,
              )
            }
            break
          }
        }
      }

      return { viewBox: `${minX} ${minY} ${vw} ${vh}`, parts: svgParts.join('\n') }
    } catch (e) {
      console.warn('Failed to build Excalidraw preview:', e)
      return null
    }
  }, [rawElements])

  if (!svgContent) return null

  function handleOpen() {
    if (onOpen) {
      onOpen()
    } else if (window.electronAPI?.openArtifactWindow) {
      if (!svgContent) return
      const fullSvg = `<!DOCTYPE html><html><head><title>Excalidraw Diagram</title></head><body style="margin:0;display:flex;justify-content:center;align-items:center;min-height:100vh;background:#fff;">` +
        `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${svgContent.viewBox}" style="max-width:100%;height:auto;">${svgContent.parts}</svg></body></html>`
      window.electronAPI.openArtifactWindow(fullSvg, 'Excalidraw Diagram')
    }
  }

  return (
    <div className="tool-visual-content tool-visual-svg" style={{ padding: 12, background: '#fff' }}>
      <div className="tool-visual-header">
        <span className="tool-visual-icon">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <polygon points="12 2 22 8.5 22 15.5 12 22 2 15.5 2 8.5" />
          </svg>
        </span>
        <span className="tool-visual-label">Excalidraw Diagram</span>
        <button className="tool-visual-open" onClick={handleOpen} title="Open in new window">
          Open
        </button>
      </div>
      <svg
        xmlns="http://www.w3.org/2000/svg"
        viewBox={svgContent.viewBox}
        style={{ maxWidth: '100%', height: 'auto', background: '#fff', borderRadius: 8 }}
        dangerouslySetInnerHTML={{ __html: svgContent.parts }}
      />
    </div>
  )
}
