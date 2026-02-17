import { useCallback, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeHighlight from 'rehype-highlight';
import { useUIStore } from '@/stores/uiStore';
import type { Components } from 'react-markdown';

interface Props {
  content: string;
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
      // Extract code text for the copy button
      let codeText = '';
      if (children && typeof children === 'object' && 'props' in (children as React.ReactElement)) {
        const codeEl = children as React.ReactElement<{ children?: React.ReactNode }>;
        if (typeof codeEl.props.children === 'string') {
          codeText = codeEl.props.children;
        }
      }

      return (
        <pre {...props} className="code-block-wrapper">
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
