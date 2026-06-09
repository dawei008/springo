/**
 * Bypass React's controlled-input gate to write into the chat textarea
 * without losing the framework's ability to observe the change.
 *
 * Why the native setter dance: setting `.value` directly on a controlled
 * <textarea> is silently overwritten by React on the next render. We use the
 * prototype setter (which React's synthetic-event system listens to) and
 * dispatch a real `input` event so React picks up the new value.
 */

interface PrefillOptions {
  /** When `true`, append to existing content instead of replacing it. */
  append?: boolean;
  /** When `true`, prepend instead of replacing. */
  prepend?: boolean;
  /** Caret position after the write; defaults to end of new value. */
  caret?: number;
  /** Focus the textarea (default true). */
  focus?: boolean;
}

export function prefillMessageInput(text: string, opts: PrefillOptions = {}): HTMLTextAreaElement | null {
  const el = document.getElementById('message-input') as HTMLTextAreaElement | null;
  if (!el) return null;

  const current = el.value || '';
  let next: string;
  if (opts.append) next = current + text;
  else if (opts.prepend) next = text + current;
  else next = text;

  const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value')?.set;
  setter?.call(el, next);
  el.dispatchEvent(new Event('input', { bubbles: true }));

  if (opts.focus !== false) el.focus();
  const caret = opts.caret ?? next.length;
  try { el.setSelectionRange(caret, caret); } catch { /* ignore — caret out of range */ }
  return el;
}
