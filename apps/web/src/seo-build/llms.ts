import type { ExplainerContent } from '../seo/content/strategies'
import type { GlossaryTerm } from '../seo/content/glossary'

export interface LlmsPage { url: string; title: string; description: string }

export function buildLlmsTxt(site: string, name: string, summary: string, pages: LlmsPage[]): string {
  const lines = pages.map((p) => `- [${p.title}](${site}${p.url}): ${p.description}`)
  return `# ${name}\n\n${summary}\n\n## Pages\n\n${lines.join('\n')}\n`
}

export function explainerToText(e: ExplainerContent): string {
  const faq = e.faq.map((f) => `Q: ${f.q}\nA: ${f.a}`).join('\n')
  return `${e.summary}\n\nWhen to use: ${e.whenToUse}\nRisk profile: ${e.riskProfile}\n\nFAQ:\n${faq}`
}

export function glossaryTermToText(t: GlossaryTerm): string {
  const faq = t.faq.map((f) => `Q: ${f.q}\nA: ${f.a}`).join('\n')
  const refs = t.sources.map((s) => `${s.label}: ${s.url}`).join('\n')
  const ex = t.example ? `\nExample: ${t.example}` : ''
  return `${t.short}\n\n${t.definition.join('\n\n')}${ex}\n\nFAQ:\n${faq}\n\nReferences:\n${refs}`
}

export interface LlmsFullEntry { title: string; url: string; body: string }
export interface LlmsFullSection { heading: string; entries: LlmsFullEntry[] }

export function buildLlmsFullTxt(
  site: string, name: string, summary: string, sections: LlmsFullSection[],
): string {
  const head = `# ${name}\n\n${summary}\n\nSite: ${site}\nSee also: ${site}/llms.txt (index)\n\nFull public learning content, provided for AI and LLM ingestion.\n`
  const body = sections
    .map((s) => {
      const entries = s.entries
        .map((e) => `### ${e.title}\nURL: ${site}${e.url}\n\n${e.body}`)
        .join('\n\n')
      return `## ${s.heading}\n\n${entries}`
    })
    .join('\n\n')
  return `${head}\n${body}\n`
}
