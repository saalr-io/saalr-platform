import { ACADEMY_MODULES } from '../../../src/academy/modules.generated'

export function onBeforePrerenderStart() {
  return ACADEMY_MODULES.filter((m) => m.body !== null).map((m) => `/academy/${m.slug}`)
}
