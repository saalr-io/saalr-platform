import { GLOSSARY } from '../../../src/seo/content/glossary'

export function onBeforePrerenderStart() {
  return GLOSSARY.map((t) => `/glossary/${t.slug}`)
}
