import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import { SafeMarkdown } from '../components/SafeMarkdown';

describe('SafeMarkdown Component', () => {
  it('renders plain text into paragraph', () => {
    const { container } = render(<SafeMarkdown content="System operational." />);
    expect(container.textContent).toContain('System operational.');
  });

  it('renders inline code and bold formatting', () => {
    const { container } = render(
      <SafeMarkdown content="Active status is `OK` and **verified**." />
    );
    const codeEl = container.querySelector('code');
    const boldEl = container.querySelector('strong');

    expect(codeEl).not.toBeNull();
    expect(codeEl?.textContent).toBe('OK');
    expect(boldEl).not.toBeNull();
    expect(boldEl?.textContent).toBe('verified');
  });

  it('renders fenced code blocks with language tag', () => {
    const code = '```python\nprint("Hello JARVIS")\n```';
    const { container } = render(<SafeMarkdown content={code} />);

    const preEl = container.querySelector('pre');
    expect(preEl).not.toBeNull();
    expect(preEl?.textContent).toContain('print("Hello JARVIS")');
    expect(container.textContent).toContain('PYTHON');
  });

  it('safely escapes raw HTML and prevents script execution', () => {
    const malicious = '<script>alert("hack")</script><img src="x" onerror="evil()" />';
    const { container } = render(<SafeMarkdown content={malicious} />);

    const scripts = container.querySelectorAll('script');
    expect(scripts.length).toBe(0);
    expect(container.textContent).toContain('<script>');
  });

  it('renders markdown links into safe anchor elements', () => {
    const content = 'Check documentation at [JARVIS Docs](https://jarvis.ai/docs).';
    const { container } = render(<SafeMarkdown content={content} />);

    const link = container.querySelector('a');
    expect(link).not.toBeNull();
    expect(link?.textContent).toBe('JARVIS Docs');
    expect(link?.getAttribute('href')).toBe('https://jarvis.ai/docs');
    expect(link?.getAttribute('target')).toBe('_blank');
    expect(link?.getAttribute('rel')).toBe('noopener noreferrer');
  });

  it('renders unordered and ordered lists with correct markers', () => {
    const content = '- First item\n- Second item\n1. Numbered item';
    const { container } = render(<SafeMarkdown content={content} />);

    expect(container.textContent).toContain('First item');
    expect(container.textContent).toContain('Second item');
    expect(container.textContent).toContain('Numbered item');
    expect(container.textContent).toContain('•');
    expect(container.textContent).toContain('1.');
  });

  it('renders blockquotes with distinctive styling', () => {
    const content = '> Power levels at 100% capacity.';
    const { container } = render(<SafeMarkdown content={content} />);

    const bq = container.querySelector('blockquote');
    expect(bq).not.toBeNull();
    expect(bq?.textContent).toContain('Power levels at 100% capacity.');
  });

  it('renders markdown tables with headers and data cells', () => {
    const tableMd = '| Parameter | Value |\n|---|---|\n| Core Status | Online |\n| Latency | 12ms |';
    const { container } = render(<SafeMarkdown content={tableMd} />);

    const table = container.querySelector('table');
    expect(table).not.toBeNull();
    const headers = container.querySelectorAll('th');
    expect(headers.length).toBe(2);
    expect(headers[0].textContent).toBe('Parameter');
    expect(headers[1].textContent).toBe('Value');

    const cells = container.querySelectorAll('td');
    expect(cells.length).toBe(4);
    expect(cells[0].textContent).toBe('Core Status');
    expect(cells[1].textContent).toBe('Online');
  });
});
