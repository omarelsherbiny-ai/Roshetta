// web/src/components/assistant/ChatText.tsx (renders the assistant's answer: tables, lists, bold; never raw HTML)
'use client';

import React from 'react';
import { inlineSpans, parseBlocks } from '@/lib/chatMarkdown';

function Inline({ text }: { text: string }) {
  return (
    <>
      {inlineSpans(text).map((span, index) => {
        if (span.kind === 'b') return <strong key={index} className="font-bold">{span.text}</strong>;
        if (span.kind === 'i') return <em key={index}>{span.text}</em>;
        if (span.kind === 'code') return <code key={index} className="rounded bg-surface-container px-1 text-[0.9em]">{span.text}</code>;
        return <React.Fragment key={index}>{span.text}</React.Fragment>;
      })}
    </>
  );
}

export function ChatText({ text }: { text: string }) {
  const blocks = parseBlocks(text);
  return (
    <div className="flex min-w-0 flex-col gap-2 font-body-md text-body-md leading-relaxed text-start break-words">
      {blocks.map((block, index) => {
        if (block.type === 'h') {
          return <p key={index} className="font-bold text-on-surface"><Inline text={block.text} /></p>;
        }
        if (block.type === 'hr') {
          return <div key={index} className="h-px w-full bg-outline-variant/40" />;
        }
        if (block.type === 'ul' || block.type === 'ol') {
          const Tag = block.type === 'ul' ? 'ul' : 'ol';
          return (
            <Tag key={index} className={`ms-5 flex flex-col gap-1 ${block.type === 'ul' ? 'list-disc' : 'list-decimal'}`}>
              {block.items.map((item, i) => <li key={i}><Inline text={item} /></li>)}
            </Tag>
          );
        }
        if (block.type === 'table') {
          return (
            <div key={index} className="max-w-full overflow-x-auto rounded-lg border border-outline-variant/40">
              <table className="w-full border-collapse text-[0.92em]">
                <thead className="bg-surface-container-low">
                  <tr>
                    {block.head.map((cell, i) => (
                      <th key={i} className="whitespace-nowrap px-2.5 py-1.5 text-start font-bold text-on-surface-variant">
                        <Inline text={cell} />
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {block.rows.map((row, r) => (
                    <tr key={r} className="border-t border-outline-variant/30">
                      {row.map((cell, c) => (
                        <td key={c} className="px-2.5 py-1.5 text-start align-top">
                          <Inline text={cell} />
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          );
        }
        return (
          <p key={index}>
            {block.lines.map((line, i) => (
              <React.Fragment key={i}>
                {i > 0 && <br />}
                <Inline text={line} />
              </React.Fragment>
            ))}
          </p>
        );
      })}
    </div>
  );
}