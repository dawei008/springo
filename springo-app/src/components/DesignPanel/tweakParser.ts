export interface TweakParam {
  id: string;
  label: string;
  cssVar: string;
  type: 'color' | 'range' | 'select';
  value: string;
  options?: string[];
  min?: number;
  max?: number;
  unit?: string;
}

const TWEAK_RE = /\/\*\s*@tweak\s+(\w+)\s*(?:\|([^*]+))?\*\//g;

export function parseTweaks(css: string): TweakParam[] {
  const tweaks: TweakParam[] = [];
  const lines = css.split('\n');

  for (let i = 0; i < lines.length; i++) {
    TWEAK_RE.lastIndex = 0;
    const match = TWEAK_RE.exec(lines[i]);
    if (!match) continue;

    const tweakType = match[1] as TweakParam['type'];
    const opts = match[2]?.trim() || '';

    const propLine = lines[i + 1] || lines[i];
    const propMatch = propLine.match(/([\w-]+)\s*:\s*(.+?)\s*;/);
    if (!propMatch) continue;

    const prop = propMatch[1];
    const value = propMatch[2].trim();

    const varMatch = value.match(/var\((--[\w-]+)/);
    const cssVar = varMatch ? varMatch[1] : `--tweak-${prop}-${tweaks.length}`;

    const param: TweakParam = {
      id: `tweak-${tweaks.length}`,
      label: prop.replace(/-/g, ' ').replace(/\b\w/g, c => c.toUpperCase()),
      cssVar,
      type: tweakType,
      value: varMatch ? '' : value,
    };

    if (tweakType === 'color') {
      param.value = param.value || '#000000';
    } else if (tweakType === 'range') {
      const numMatch = (param.value || '16px').match(/([\d.]+)(.*)/);
      param.value = numMatch ? numMatch[1] : '16';
      param.unit = numMatch ? numMatch[2] || 'px' : 'px';
      const rangeOpts = opts.split(',').map(s => s.trim());
      param.min = parseFloat(rangeOpts[0]) || 0;
      param.max = parseFloat(rangeOpts[1]) || 100;
    } else if (tweakType === 'select') {
      param.options = opts.split(',').map(s => s.trim()).filter(Boolean);
      param.value = param.value || param.options[0] || '';
    }

    tweaks.push(param);
  }

  return tweaks;
}
