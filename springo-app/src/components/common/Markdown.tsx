import { useCallback, useState, isValidElement } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeHighlight from 'rehype-highlight';
import { useUIStore } from '@/stores/uiStore';
import type { Components } from 'react-markdown';

interface Props {
  content: string;
}

/**
 * Extract plain text from React children tree (used for code copy button).
 */
function extractText(children: React.ReactNode): string {
  if (typeof children === 'string') return children;
  if (typeof children === 'number') return String(children);
  if (!children) return '';
  if (Array.isArray(children)) {
    return children.map(extractText).join('');
  }
  if (isValidElement(children)) {
    const props = children.props as Record<string, unknown>;
    return extractText(props.children as React.ReactNode);
  }
  return '';
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }, [text]);

  return (
    <button className="copy-code-btn" onClick={handleCopy}>
      {copied ? 'Copied!' : 'Copy'}
    </button>
  );
}

export default function Markdown({ content }: Props) {
  const components: Components = {
    pre({ children, ...props }) {
      // Extract code text from children for the copy button
      const codeText = extractText(children);

      return (
        <pre {...props}>
          {children}
          {codeText && <CopyButton text={codeText} />}
        </pre>
      );
    },

    a({ href, children, ...props }) {
      const handleClick = (e: React.MouseEvent<HTMLAnchorElement>) => {
        e.preventDefault();
        if (href) {
          if (window.electronAPI?.openExternal) {
            window.electronAPI.openExternal(href);
          } else {
            window.open(href, '_blank', 'noopener,noreferrer');
          }
        }
      };

      return (
        <a
          {...props}
          href={href}
          onClick={handleClick}
          className="clickable-url"
          title={href}
        >
          {children}
        </a>
      );
    },

    img({ src, alt, ...props }) {
      const handleClick = () => {
        if (src) {
          useUIStore.getState().setImagePreview(src);
        }
      };

      return (
        <img
          {...props}
          src={src}
          alt={alt}
          className="chat-image"
          onClick={handleClick}
          style={{ maxWidth: '100%', cursor: 'pointer', borderRadius: 8 }}
        />
      );
    },
  };

  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      rehypePlugins={[rehypeHighlight]}
      components={components}
    >
      {content}
    </ReactMarkdown>
  );
}
