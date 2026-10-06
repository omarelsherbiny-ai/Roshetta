// web/src/lib/chatMarkdown.ts (pure parser for the assistant's answers: a small markdown subset, no HTML)

export type MdBlock =
  | { type: 'p'; lines: string[] }
  | { type: 'h'; level: number; text: string }
  | { type: 'ul' | 'ol'; items: string[] }
  | { type: 'table'; head: string[]; rows: string[][] }
  | { type: 'hr' };

export interface MdSpan {
  kind: 'text' | 'b' | 'i' | 'code';
  text: string;
}

const SEPARATOR_ROW = /^\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?$/;

function splitRow(line: string): string[] {
  let body = line.trim();
  if (body.startsWith('|')) body = body.slice(1);
  if (body.endsWith('|')) body = body.slice(0, -1);
  return body.split('|').map((cell) => cell.trim());
}

/** Bold, italic and code spans of one line. Everything else stays plain text (React escapes it). */
export function inlineSpans(text: string): MdSpan[] {
  const spans: MdSpan[] = [];
  const pattern = /(\*\*[^*]+?\*\*|`[^`]+`|\*[^*\s][^*]*?\*)/g;
  let last = 0;
  let match: RegExpExecArray | null;
  while ((match = pattern.exec(text)) !== null) {
    if (match.index > last) spans.push({ kind: 'text', text: text.slice(last, match.index) });
    const token = match[0];
    if (token.startsWith('**')) spans.push({ kind: 'b', text: token.slice(2, -2) });
    else if (token.startsWith('`')) spans.push({ kind: 'code', text: token.slice(1, -1) });
    else spans.push({ kind: 'i', text: token.slice(1, -1) });
    last = match.index + token.length;
  }
  if (last < text.length) spans.push({ kind: 'text', text: text.slice(last) });
  return spans;
}

export function parseBlocks(source: string): MdBlock[] {
  const lines = source.replace(/\r\n/g, '\n').split('\n');
  const blocks: MdBlock[] = [];
  let paragraph: string[] = [];
  const flush = () => {
    if (paragraph.length) blocks.push({ type: 'p', lines: paragraph });
    paragraph = [];
  };

  for (let i = 0; i < lines.length; i += 1) {
    const line = lines[i];
    const trimmed = line.trim();
    if (trimmed === '') { flush(); continue; }

    if (trimmed.startsWith('|') && i + 1 < lines.length && SEPARATOR_ROW.test(lines[i + 1].trim())) {
      flush();
      const head = splitRow(trimmed);
      const rows: string[][] = [];
      i += 2;
      while (i < lines.length && lines[i].trim().startsWith('|')) {
        rows.push(splitRow(lines[i]));
        i += 1;
      }
      i -= 1;
      blocks.push({ type: 'table', head, rows });
      continue;
    }

    const heading = /^(#{1,4})\s+(.*)$/.exec(trimmed);
    if (heading) { flush(); blocks.push({ type: 'h', level: heading[1].length, text: heading[2] }); continue; }

    if (/^(-{3,}|\*{3,})$/.test(trimmed)) { flush(); blocks.push({ type: 'hr' }); continue; }

    const bullet = /^[-*•]\s+(.*)$/.exec(trimmed);
    const numbered = /^\d+[.)]\s+(.*)$/.exec(trimmed);
    if (bullet || numbered) {
      flush();
      const type = bullet ? 'ul' : 'ol';
      const items: string[] = [];
      while (i < lines.length) {
        const current = lines[i].trim();
        const b = /^[-*•]\s+(.*)$/.exec(current);
        const n = /^\d+[.)]\s+(.*)$/.exec(current);
        const item = type === 'ul' ? b : n;
        if (!item) break;
        items.push(item[1]);
        i += 1;
      }
      i -= 1;
      blocks.push({ type, items });
      continue;
    }

    paragraph.push(trimmed);
  }
  flush();
  return blocks;
}