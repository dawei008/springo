/**
 * Read an SSE response body and dispatch each `data: ...` event.
 * Skips `[DONE]` sentinels and unparseable JSON without throwing.
 */
export async function readSseEvents(
  response: Response,
  onEvent: (event: Record<string, unknown>) => void,
): Promise<void> {
  const reader = response.body?.getReader();
  if (!reader) throw new Error('No response body');

  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() || '';

    for (const line of lines) {
      if (!line.startsWith('data: ')) continue;
      const data = line.slice(6).trim();
      if (data === '[DONE]') continue;
      try {
        onEvent(JSON.parse(data));
      } catch {
        // skip unparseable lines
      }
    }
  }
}
