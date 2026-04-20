/**
 * DesignExport - export utility functions
 */
import { api } from '@/services/api';

export function exportHtml(html: string, title: string) {
  const blob = new Blob([html], { type: 'text/html' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `${title || 'design'}.html`;
  a.click();
  URL.revokeObjectURL(url);
}

export async function exportPng(): Promise<void> {
  // PNG export requires Electron IPC — will be added when main process support is ready
  console.warn('PNG export not yet implemented');
}

export async function exportPdf(html: string, title: string): Promise<void> {
  const resp = await api.design.exportPdf(html);
  if (resp.ok && resp.data) {
    const blob = resp.data as unknown as Blob;
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${title || 'design'}.pdf`;
    a.click();
    URL.revokeObjectURL(url);
  }
}

export async function exportPptx(html: string, title: string): Promise<void> {
  const resp = await api.design.exportPptx(html);
  if (resp.ok && resp.data) {
    const blob = resp.data as unknown as Blob;
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${title || 'design'}.pptx`;
    a.click();
    URL.revokeObjectURL(url);
  }
}
