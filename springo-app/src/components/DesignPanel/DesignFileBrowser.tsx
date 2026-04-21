/**
 * DesignFileBrowser - file tree grouped by category (Pages, Components, Stylesheets)
 */
import { useDesignStore, selectCurrentDesign } from '@/stores/designStore';
import type { DesignFile, DesignFileType } from '@/types';

interface FileGroup {
  label: string;
  icon: string; // SVG path
  types: DesignFileType[];
  files: DesignFile[];
}

function groupFiles(files: DesignFile[]): FileGroup[] {
  const groups: FileGroup[] = [
    { label: 'PAGES', icon: 'M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z', types: ['html'], files: [] },
    { label: 'COMPONENTS', icon: 'M13 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V9l-7-7z', types: ['jsx'], files: [] },
    { label: 'STYLESHEETS', icon: 'M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5', types: ['css'], files: [] },
    { label: 'OTHER', icon: 'M13 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V9z', types: ['json', 'text'], files: [] },
  ];
  for (const file of files) {
    const group = groups.find(g => g.types.includes(file.type)) || groups[groups.length - 1];
    group.files.push(file);
  }
  return groups.filter(g => g.files.length > 0);
}

function fileTypeColor(type: DesignFileType): string {
  switch (type) {
    case 'html': return '#e44d26';
    case 'jsx': return '#61dafb';
    case 'css': return '#264de4';
    case 'json': return '#f5a623';
    default: return '#999';
  }
}

function fileName(path: string): string {
  return path.split('/').pop() || path;
}

function fileSubtype(path: string): string {
  if (path.endsWith('.html')) return 'HTML page';
  if (path.endsWith('.jsx') || path.endsWith('.tsx')) return 'Component';
  if (path.endsWith('.css')) return 'Stylesheet';
  if (path.endsWith('.json')) return 'JSON';
  return 'File';
}

export default function DesignFileBrowser() {
  const design = useDesignStore(selectCurrentDesign);
  const activeFilePath = useDesignStore((s) => s.activeFilePath);
  const selectFile = useDesignStore((s) => s.selectFile);

  if (!design || !design.files || design.files.length === 0) return null;

  const groups = groupFiles(design.files);

  return (
    <div className="design-file-browser">
      {groups.map(group => (
        <div key={group.label} className="design-file-group">
          <div className="design-file-group-header">
            <span className="design-file-group-label">{group.label}</span>
          </div>
          {group.files.map(file => (
            <div
              key={file.path}
              className={`design-file-item${activeFilePath === file.path ? ' active' : ''}`}
              onClick={() => selectFile(file.path)}
              title={file.path}
            >
              <div
                className="design-file-icon"
                style={{ backgroundColor: fileTypeColor(file.type) }}
              />
              <div className="design-file-info">
                <span className="design-file-name">{fileName(file.path)}</span>
                <span className="design-file-type">{fileSubtype(file.path)}</span>
              </div>
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}
