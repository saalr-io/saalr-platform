import type React from 'react'

// ── inline parser ──────────────────────────────────────────────────────────
// Handles: **bold**, *italic*, `code` — returns React nodes (never raw HTML).

type InlineToken =
  | { type: 'text'; value: string }
  | { type: 'bold'; value: string }
  | { type: 'italic'; value: string }
  | { type: 'code'; value: string }

function parseInline(src: string): InlineToken[] {
  const tokens: InlineToken[] = []
  let i = 0
  while (i < src.length) {
    // bold **...**
    if (src[i] === '*' && src[i + 1] === '*') {
      const end = src.indexOf('**', i + 2)
      if (end !== -1) {
        tokens.push({ type: 'bold', value: src.slice(i + 2, end) })
        i = end + 2
        continue
      }
    }
    // italic *...*
    if (src[i] === '*') {
      const end = src.indexOf('*', i + 1)
      if (end !== -1) {
        tokens.push({ type: 'italic', value: src.slice(i + 1, end) })
        i = end + 1
        continue
      }
    }
    // inline code `...`
    if (src[i] === '`') {
      const end = src.indexOf('`', i + 1)
      if (end !== -1) {
        tokens.push({ type: 'code', value: src.slice(i + 1, end) })
        i = end + 1
        continue
      }
    }
    // accumulate plain text
    const next = src.indexOf('*', i)
    const nextTick = src.indexOf('`', i)
    let stop = src.length
    if (next !== -1 && next < stop) stop = next
    if (nextTick !== -1 && nextTick < stop) stop = nextTick
    tokens.push({ type: 'text', value: src.slice(i, stop) })
    i = stop
  }
  return tokens
}

function renderInline(src: string, keyPrefix: string): React.ReactNode[] {
  return parseInline(src).map((tok, idx) => {
    const key = `${keyPrefix}-${idx}`
    switch (tok.type) {
      case 'bold':
        return <strong key={key} className="font-semibold text-txt">{tok.value}</strong>
      case 'italic':
        return <em key={key} className="italic">{tok.value}</em>
      case 'code':
        return (
          <code key={key} className="rounded bg-panel2 px-1 py-0.5 font-mono text-[0.85em] text-accent">
            {tok.value}
          </code>
        )
      default:
        return tok.value
    }
  })
}

// ── block parser ───────────────────────────────────────────────────────────

type BlockNode =
  | { type: 'h1' | 'h2' | 'h3'; text: string }
  | { type: 'p'; text: string }
  | { type: 'ul'; items: string[] }
  | { type: 'ol'; items: string[] }
  | { type: 'blank' }

function parseBlocks(src: string): BlockNode[] {
  // Normalize CRLF/CR so a trailing \r can't corrupt heading/list detection or
  // leak into rendered text (lesson bodies may be Windows-authored).
  const lines = src.replace(/\r\n?/g, '\n').split('\n')
  const nodes: BlockNode[] = []
  let i = 0

  while (i < lines.length) {
    const line = lines[i]

    // headings
    if (line.startsWith('### ')) { nodes.push({ type: 'h3', text: line.slice(4) }); i++; continue }
    if (line.startsWith('## '))  { nodes.push({ type: 'h2', text: line.slice(3) }); i++; continue }
    if (line.startsWith('# '))   { nodes.push({ type: 'h1', text: line.slice(2) }); i++; continue }

    // blank line
    if (line.trim() === '') { nodes.push({ type: 'blank' }); i++; continue }

    // unordered list — consume consecutive `- ` lines
    if (/^- /.test(line)) {
      const items: string[] = []
      while (i < lines.length && /^- /.test(lines[i])) {
        items.push(lines[i].slice(2))
        i++
      }
      nodes.push({ type: 'ul', items })
      continue
    }

    // ordered list — consume consecutive `N. ` lines
    if (/^\d+\. /.test(line)) {
      const items: string[] = []
      while (i < lines.length && /^\d+\. /.test(lines[i])) {
        items.push(lines[i].replace(/^\d+\. /, ''))
        i++
      }
      nodes.push({ type: 'ol', items })
      continue
    }

    // paragraph — consume until blank or heading
    const paras: string[] = []
    while (
      i < lines.length &&
      lines[i].trim() !== '' &&
      !lines[i].startsWith('#') &&
      !/^- /.test(lines[i]) &&
      !/^\d+\. /.test(lines[i])
    ) {
      paras.push(lines[i])
      i++
    }
    if (paras.length) nodes.push({ type: 'p', text: paras.join(' ') })
  }

  return nodes
}

// ── React component ────────────────────────────────────────────────────────

interface MarkdownProps {
  source: string
}

export function Markdown({ source }: MarkdownProps) {
  const blocks = parseBlocks(source)

  return (
    <div className="space-y-3 text-sm leading-relaxed text-txtDim">
      {blocks.map((block, bi) => {
        const key = `b${bi}`
        switch (block.type) {
          case 'h1':
            return (
              <h2 key={key} className="text-lg font-semibold tracking-tight text-txt">
                {renderInline(block.text, key)}
              </h2>
            )
          case 'h2':
            return (
              <h3 key={key} className="text-base font-semibold tracking-tight text-txt">
                {renderInline(block.text, key)}
              </h3>
            )
          case 'h3':
            return (
              <h4 key={key} className="text-sm font-semibold uppercase tracking-[0.12em] text-txtDim">
                {renderInline(block.text, key)}
              </h4>
            )
          case 'p':
            return (
              <p key={key} className="text-txtDim">
                {renderInline(block.text, key)}
              </p>
            )
          case 'ul':
            return (
              <ul key={key} className="space-y-1 pl-4">
                {block.items.map((item, ii) => (
                  <li key={ii} className="flex gap-2">
                    <span aria-hidden className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-accent" />
                    <span>{renderInline(item, `${key}-li${ii}`)}</span>
                  </li>
                ))}
              </ul>
            )
          case 'ol':
            return (
              <ol key={key} className="space-y-1 pl-4">
                {block.items.map((item, ii) => (
                  <li key={ii} className="flex gap-2">
                    <span aria-hidden className="shrink-0 font-mono text-[11px] text-accent">{ii + 1}.</span>
                    <span>{renderInline(item, `${key}-li${ii}`)}</span>
                  </li>
                ))}
              </ol>
            )
          default:
            return null
        }
      })}
    </div>
  )
}
