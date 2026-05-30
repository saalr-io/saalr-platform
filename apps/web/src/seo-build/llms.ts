export interface LlmsPage { url: string; title: string; description: string }

export function buildLlmsTxt(site: string, name: string, summary: string, pages: LlmsPage[]): string {
  const lines = pages.map((p) => `- [${p.title}](${site}${p.url}): ${p.description}`)
  return `# ${name}\n\n${summary}\n\n## Pages\n\n${lines.join('\n')}\n`
}
