import { EXPLAINERS } from '../../../src/seo/content/strategies'

export function onBeforePrerenderStart() {
  return EXPLAINERS.map((e) => `/learn/${e.slug}`)
}
