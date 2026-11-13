import React from 'react';

interface SafeMarkdownProps {
  content: string;
}

export const SafeMarkdown: React.FC<SafeMarkdownProps> = ({ content }) => {
  // Parse lines into tokens: code blocks, tables, headings, lists, blockquotes, paragraphs
  const tokens: Array<
    | { type: 'code_block'; lang: string; code: string }
    | { type: 'heading'; level: number; text: string }
    | { type: 'list_item'; text: string; ordered: boolean; num?: number }
    | { type: 'blockquote'; text: string }
    | { type: 'table'; headers: string[]; rows: string[][] }
    | { type: 'paragraph'; text: string }
  > = [];

  const lines = content.split('\n');
  let inCodeBlock = false;
  let codeLang = '';
  let codeBuffer: string[] = [];

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];

    if (line.trim().startsWith('```')) {
      if (inCodeBlock) {
        tokens.push({
          type: 'code_block',
          lang: codeLang,
          code: codeBuffer.join('\n'),
        });
        inCodeBlock = false;
        codeLang = '';
        codeBuffer = [];
      } else {
        inCodeBlock = true;
        codeLang = line.trim().replace(/^```/, '').trim();
      }
      continue;
    }

    if (inCodeBlock) {
      codeBuffer.push(line);
      continue;
    }

    // Table detection: line starting and ending with '|'
    if (line.trim().startsWith('|') && line.trim().endsWith('|')) {
      const tableLines: string[] = [line];
      while (i + 1 < lines.length && lines[i + 1].trim().startsWith('|') && lines[i + 1].trim().endsWith('|')) {
        i++;
        tableLines.push(lines[i]);
      }
      if (tableLines.length >= 2) {
        const parseRow = (r: string) =>
          r
            .trim()
            .slice(1, -1)
            .split('|')
            .map((c) => c.trim());
        const headers = parseRow(tableLines[0]);
        const isDelimiter = (r: string) => r.replace(/[\s\-\|:]/g, '').length === 0;
        const dataRows = tableLines.slice(1).filter((r) => !isDelimiter(r)).map(parseRow);
        tokens.push({
          type: 'table',
          headers,
          rows: dataRows,
        });
        continue;
      }
    }

    // Heading
    if (line.startsWith('#')) {
      const match = line.match(/^(#{1,3})\s+(.*)$/);
      if (match) {
        tokens.push({
          type: 'heading',
          level: match[1].length,
          text: match[2],
        });
        continue;
      }
    }

    // Blockquote
    if (line.startsWith('>')) {
      tokens.push({
        type: 'blockquote',
        text: line.replace(/^>\s?/, ''),
      });
      continue;
    }

    // List item
    const unorderedMatch = line.match(/^[\*\-]\s+(.*)$/);
    if (unorderedMatch) {
      tokens.push({
        type: 'list_item',
        ordered: false,
        text: unorderedMatch[1],
      });
      continue;
    }

    const orderedMatch = line.match(/^(\d+)\.\s+(.*)$/);
    if (orderedMatch) {
      tokens.push({
        type: 'list_item',
        ordered: true,
        num: parseInt(orderedMatch[1], 10),
        text: orderedMatch[2],
      });
      continue;
    }

    if (line.trim()) {
      tokens.push({
        type: 'paragraph',
        text: line,
      });
    }
  }

  // Close unclosed code block if stream is mid-transmission
  if (inCodeBlock && codeBuffer.length > 0) {
    tokens.push({
      type: 'code_block',
      lang: codeLang,
      code: codeBuffer.join('\n'),
    });
  }

  // Helper to render bold, italic, inline code, and links safely
  const renderInline = (text: string): React.ReactNode[] => {
    const parts: React.ReactNode[] = [];
    const regex = /(`[^`]+`|\*\*[^*]+\*\*|\*[^*]+\*|\[[^\]]+\]\([^)]+\))/g;
    let lastIndex = 0;
    let match;

    while ((match = regex.exec(text)) !== null) {
      if (match.index > lastIndex) {
        parts.push(text.substring(lastIndex, match.index));
      }

      const matchStr = match[0];
      if (matchStr.startsWith('`') && matchStr.endsWith('`')) {
        parts.push(
          <code
            key={match.index}
            style={{
              background: 'rgba(0, 229, 255, 0.12)',
              border: '1px solid rgba(0, 229, 255, 0.3)',
              padding: '0.12rem 0.38rem',
              borderRadius: '3px',
              fontFamily: 'var(--hud-font-mono)',
              fontSize: '0.85em',
              color: 'var(--chat-accent-cyan, #00e5ff)',
            }}
          >
            {matchStr.slice(1, -1)}
          </code>
        );
      } else if (matchStr.startsWith('**') && matchStr.endsWith('**')) {
        parts.push(
          <strong key={match.index} style={{ color: '#FFFFFF', fontWeight: 700 }}>
            {matchStr.slice(2, -2)}
          </strong>
        );
      } else if (matchStr.startsWith('*') && matchStr.endsWith('*')) {
        parts.push(
          <em key={match.index} style={{ color: 'var(--chat-text-secondary, #B0B7C3)', fontStyle: 'italic' }}>
            {matchStr.slice(1, -1)}
          </em>
        );
      } else if (matchStr.startsWith('[') && matchStr.endsWith(')')) {
        const linkMatch = matchStr.match(/^\[([^\]]+)\]\(([^)]+)\)$/);
        if (linkMatch) {
          parts.push(
            <a
              key={match.index}
              href={linkMatch[2]}
              target="_blank"
              rel="noopener noreferrer"
              style={{
                color: 'var(--chat-accent-cyan, #00e5ff)',
                textDecoration: 'underline',
                textUnderlineOffset: '2px',
                wordBreak: 'break-all',
              }}
            >
              {linkMatch[1]}
            </a>
          );
        } else {
          parts.push(matchStr);
        }
      }

      lastIndex = regex.lastIndex;
    }

    if (lastIndex < text.length) {
      parts.push(text.substring(lastIndex));
    }

    return parts;
  };

  return (
    <div className="safe-markdown" style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
      {tokens.map((token, idx) => {
        switch (token.type) {
          case 'code_block':
            return (
              <div
                key={idx}
                style={{
                  background: 'rgba(6, 11, 20, 0.95)',
                  border: '1px solid rgba(0, 229, 255, 0.25)',
                  borderRadius: '4px',
                  overflow: 'hidden',
                  margin: '0.35rem 0',
                  boxShadow: '0 4px 16px rgba(0, 0, 0, 0.55)',
                }}
              >
                {token.lang && (
                  <div
                    style={{
                      background: 'rgba(0, 229, 255, 0.10)',
                      padding: '0.22rem 0.6rem',
                      fontSize: '0.7rem',
                      fontFamily: 'var(--hud-font-mono)',
                      color: 'var(--chat-accent-cyan, #00e5ff)',
                      borderBottom: '1px solid rgba(0, 229, 255, 0.2)',
                      fontWeight: 600,
                      letterSpacing: '0.05em',
                    }}
                  >
                    {token.lang.toUpperCase()}
                  </div>
                )}
                <pre
                  style={{
                    padding: '0.6rem 0.75rem',
                    overflowX: 'auto',
                    fontFamily: 'var(--hud-font-mono)',
                    fontSize: '0.8rem',
                    color: '#f1f5f9',
                    lineHeight: '1.45',
                  }}
                >
                  <code>{token.code}</code>
                </pre>
              </div>
            );

          case 'heading':
            const headingContent = renderInline(token.text);
            const headingStyle: React.CSSProperties = {
              fontFamily: 'var(--hud-font-hud)',
              color:
                token.level === 1
                  ? 'var(--chat-accent-cyan, #00e5ff)'
                  : token.level === 2
                  ? 'var(--chat-accent-blue, #38bdf8)'
                  : 'var(--chat-text-primary, #F1F3F5)',
              fontSize: token.level === 1 ? '1.02rem' : token.level === 2 ? '0.92rem' : '0.84rem',
              letterSpacing: '0.08em',
              fontWeight: 700,
              marginTop: '0.25rem',
              marginBottom: '0.1rem',
            };
            if (token.level === 1) {
              return <h1 key={idx} style={headingStyle}>{headingContent}</h1>;
            }
            if (token.level === 2) {
              return <h2 key={idx} style={headingStyle}>{headingContent}</h2>;
            }
            return <h3 key={idx} style={headingStyle}>{headingContent}</h3>;

          case 'blockquote':
            return (
              <blockquote
                key={idx}
                style={{
                  borderLeft: '3px solid var(--chat-accent-cyan, #00e5ff)',
                  background: 'rgba(0, 229, 255, 0.05)',
                  padding: '0.35rem 0.65rem',
                  borderRadius: '0 4px 4px 0',
                  color: 'var(--chat-text-secondary, #B0B7C3)',
                  fontStyle: 'italic',
                  fontSize: '0.84rem',
                  lineHeight: '1.5',
                }}
              >
                {renderInline(token.text)}
              </blockquote>
            );

          case 'list_item':
            return (
              <div key={idx} style={{ display: 'flex', gap: '0.45rem', paddingLeft: '0.35rem', lineHeight: '1.5' }}>
                <span style={{ color: 'var(--chat-accent-cyan, #00e5ff)', fontWeight: 600, minWidth: '0.9rem' }}>
                  {token.ordered ? `${token.num}.` : '•'}
                </span>
                <div style={{ color: 'var(--chat-text-primary, #F1F3F5)', fontSize: '0.84rem' }}>
                  {renderInline(token.text)}
                </div>
              </div>
            );

          case 'table':
            return (
              <div
                key={idx}
                style={{
                  margin: '0.4rem 0',
                  overflowX: 'auto',
                  border: '1px solid rgba(0, 229, 255, 0.22)',
                  borderRadius: '6px',
                  background: 'rgba(6, 12, 22, 0.90)',
                }}
              >
                <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.8rem' }}>
                  <thead>
                    <tr style={{ background: 'rgba(0, 229, 255, 0.12)', borderBottom: '1px solid rgba(0, 229, 255, 0.25)' }}>
                      {token.headers.map((h, hIdx) => (
                        <th
                          key={hIdx}
                          style={{
                            padding: '0.4rem 0.65rem',
                            color: 'var(--chat-accent-cyan, #00e5ff)',
                            fontFamily: 'var(--hud-font-hud)',
                            letterSpacing: '0.05em',
                            fontSize: '0.75rem',
                          }}
                        >
                          {renderInline(h)}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {token.rows.map((row, rIdx) => (
                      <tr
                        key={rIdx}
                        style={{
                          borderBottom: rIdx < token.rows.length - 1 ? '1px solid rgba(255, 255, 255, 0.08)' : 'none',
                        }}
                      >
                        {row.map((cell, cIdx) => (
                          <td
                            key={cIdx}
                            style={{
                              padding: '0.35rem 0.65rem',
                              color: 'var(--chat-text-primary, #F1F3F5)',
                            }}
                          >
                            {renderInline(cell)}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            );

          case 'paragraph':
          default:
            return (
              <p
                key={idx}
                style={{
                  color: 'var(--chat-text-primary, #F1F3F5)',
                  lineHeight: '1.55',
                  fontSize: '0.84rem',
                  margin: 0,
                }}
              >
                {renderInline(token.text)}
              </p>
            );
        }
      })}
    </div>
  );
};

