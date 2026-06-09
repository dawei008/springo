/** Short random id with a domain prefix. e.g. `genId('art')` → `art-1714000000000-a3f9b1`. */
export function genId(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}
