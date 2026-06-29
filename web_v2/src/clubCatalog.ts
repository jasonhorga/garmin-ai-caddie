// The canonical club catalog for the web manual club-bag editor. Tokens MUST match the backend
// club vocabulary (ai_caddie/caddie/club_catalog.py) so a PUT to /clubs/bag isn't 422'd. zhName +
// category are display-only; the backend resolves its own zhName/clubTypeId from the token.

export type ClubCategory = '木杆' | '混合杆' | '铁杆' | '挖起杆' | '推杆'
export interface CatalogClub {
  token: string
  zhName: string
  category: ClubCategory
}

export const CLUB_CATEGORIES: ClubCategory[] = ['木杆', '混合杆', '铁杆', '挖起杆', '推杆']

// Tokens MUST match the backend club_catalog.py vocabulary (so PUTs aren't 422'd).
export const CLUB_CATALOG: CatalogClub[] = [
  { token: 'driver', zhName: '一号木', category: '木杆' },
  { token: 'wood3', zhName: '三号木', category: '木杆' },
  { token: 'wood5', zhName: '五号木', category: '木杆' },
  { token: 'wood7', zhName: '七号木', category: '木杆' },
  { token: 'hybrid1', zhName: '一号小鸡腿', category: '混合杆' },
  { token: 'hybrid2', zhName: '二号小鸡腿', category: '混合杆' },
  { token: 'hybrid3', zhName: '三号小鸡腿', category: '混合杆' },
  { token: 'hybrid4', zhName: '四号小鸡腿', category: '混合杆' },
  { token: 'hybrid5', zhName: '五号小鸡腿', category: '混合杆' },
  { token: 'hybrid6', zhName: '六号小鸡腿', category: '混合杆' },
  { token: 'iron1', zhName: '一号铁', category: '铁杆' },
  { token: 'iron2', zhName: '二号铁', category: '铁杆' },
  { token: 'iron3', zhName: '三号铁', category: '铁杆' },
  { token: 'iron4', zhName: '四号铁', category: '铁杆' },
  { token: 'iron5', zhName: '五号铁', category: '铁杆' },
  { token: 'iron6', zhName: '六号铁', category: '铁杆' },
  { token: 'iron7', zhName: '七号铁', category: '铁杆' },
  { token: 'iron8', zhName: '八号铁', category: '铁杆' },
  { token: 'iron9', zhName: '九号铁', category: '铁杆' },
  { token: 'pw', zhName: 'P杆', category: '挖起杆' },
  { token: 'gw', zhName: 'A杆', category: '挖起杆' },
  { token: 'sw', zhName: 'S杆', category: '挖起杆' },
  { token: 'lw', zhName: 'L杆', category: '挖起杆' },
  { token: 'wedge50', zhName: '50°', category: '挖起杆' },
  { token: 'wedge52', zhName: '52°', category: '挖起杆' },
  { token: 'wedge54', zhName: '54°', category: '挖起杆' },
  { token: 'wedge56', zhName: '56°', category: '挖起杆' },
  { token: 'wedge58', zhName: '58°', category: '挖起杆' },
  { token: 'wedge60', zhName: '60°', category: '挖起杆' },
  { token: 'putter', zhName: '推杆', category: '推杆' },
]

export function catalogByCategory(c: ClubCategory): CatalogClub[] {
  return CLUB_CATALOG.filter((x) => x.category === c)
}

export const METRES_PER_YARD = 0.9144
