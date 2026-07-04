// Shared club display + join helpers for the 球包 page. The bag (EffectiveClubBag)
// is keyed by CANONICAL catalog tokens ('driver' / 'iron5' / 'pw'); the measured
// per-club stats (history_stats clubs[]) are keyed by short Garmin-style CODES
// ('1D' / '5I' / 'PW'). `normalizeMeasuredClubToken` maps a measured code onto a
// catalog token so the measured dispersion/sample can enrich the matching bag club.
// Matching only powers ENRICHMENT — an unmatched measured code simply doesn't
// enrich any club, so a dirty/unknown code never breaks the editable bag.

import { CLUB_CATALOG } from './clubCatalog'

// Compact ladder labels ('1W' / '5i' / 'PW' / '52°' / 'PT') derived from the
// canonical token. Full Chinese names come from the bag's zhName.
const SHORT_LABEL: Record<string, string> = {
  driver: '1W',
  wood3: '3W',
  wood5: '5W',
  wood7: '7W',
  hybrid1: '1H',
  hybrid2: '2H',
  hybrid3: '3H',
  hybrid4: '4H',
  hybrid5: '5H',
  hybrid6: '6H',
  iron1: '1i',
  iron2: '2i',
  iron3: '3i',
  iron4: '4i',
  iron5: '5i',
  iron6: '6i',
  iron7: '7i',
  iron8: '8i',
  iron9: '9i',
  pw: 'PW',
  gw: 'GW',
  sw: 'SW',
  lw: 'LW',
  wedge50: '50°',
  wedge52: '52°',
  wedge54: '54°',
  wedge56: '56°',
  wedge58: '58°',
  wedge60: '60°',
  putter: 'PT',
}

const CATALOG_TOKENS = new Set(CLUB_CATALOG.map((c) => c.token))

export function shortClubLabel(token: string): string {
  return SHORT_LABEL[token] ?? token.toUpperCase()
}

// Sort order for a ladder / bag list: longest club first, unknown tokens last.
// Purely a display fallback — the page sorts by real carry distance when present.
const TOKEN_ORDER: string[] = [
  'driver',
  'wood3',
  'wood5',
  'wood7',
  'hybrid1',
  'hybrid2',
  'hybrid3',
  'hybrid4',
  'hybrid5',
  'hybrid6',
  'iron1',
  'iron2',
  'iron3',
  'iron4',
  'iron5',
  'iron6',
  'iron7',
  'iron8',
  'iron9',
  'pw',
  'gw',
  'wedge50',
  'wedge52',
  'wedge54',
  'sw',
  'wedge56',
  'wedge58',
  'lw',
  'wedge60',
  'putter',
]

export function tokenRank(token: string): number {
  const index = TOKEN_ORDER.indexOf(token)
  return index === -1 ? TOKEN_ORDER.length : index
}

// Map a measured Garmin-style club CODE onto a canonical catalog token, or null
// if it can't be resolved to a club we carry a token for. Best-effort + forgiving:
// case-insensitive, tolerant of a trailing "退役"/degree symbol, whitespace.
export function normalizeMeasuredClubToken(rawCode: string | null | undefined): string | null {
  if (!rawCode) return null
  const s = rawCode
    .trim()
    .toUpperCase()
    .replace(/[·\s]*退役$/, '')
    .replace(/°/g, '')
    .replace(/\s+/g, '')
  if (!s) return null

  // Driver: '1D' / 'D' / 'DR' / 'DRIVER' / '1W' / 'W1'.
  if (['1D', 'D', 'DR', 'DRIVER', '1W', 'W1'].includes(s)) return 'driver'

  // Fairway woods: '3W' / 'W3'. n=1 already handled as the driver above.
  const wood = /^(?:(\d)W|W(\d))$/.exec(s)
  if (wood) {
    const n = Number(wood[1] ?? wood[2])
    if (n === 1) return 'driver'
    const token = `wood${n}`
    return CATALOG_TOKENS.has(token) ? token : null
  }

  // Hybrids / rescues: '3H' / '3HY' / 'H3' / '3R'.
  const hybrid = /^(?:(\d)(?:H|HY|R)|H(\d))$/.exec(s)
  if (hybrid) {
    const n = Number(hybrid[1] ?? hybrid[2])
    const token = `hybrid${n}`
    return CATALOG_TOKENS.has(token) ? token : null
  }

  // Irons: '5I' / 'I5'.
  const iron = /^(?:(\d)I|I(\d))$/.exec(s)
  if (iron) {
    const n = Number(iron[1] ?? iron[2])
    const token = `iron${n}`
    return CATALOG_TOKENS.has(token) ? token : null
  }

  // Named wedges.
  if (s === 'PW') return 'pw'
  if (s === 'GW' || s === 'AW' || s === 'A') return 'gw'
  if (s === 'SW') return 'sw'
  if (s === 'LW') return 'lw'

  // Degree-lofted wedges: '52' / '56'.
  const degree = /^(\d{2})$/.exec(s)
  if (degree) {
    const token = `wedge${degree[1]}`
    return CATALOG_TOKENS.has(token) ? token : null
  }

  // Putter: 'PT' / 'PUT' / 'PUTTER'. Bare 'P' is left unresolved (ambiguous vs PW).
  if (s === 'PT' || s === 'PUT' || s === 'PUTTER') return 'putter'

  return null
}
