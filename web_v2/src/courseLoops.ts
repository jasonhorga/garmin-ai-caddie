/**
 * The canonical whole physical course as a `loops=` value (B4b-2): an 18-hole course is its two
 * halves in order, a nine-hole loop is itself.
 */
export function wholeCourseLoops(globalId: number, holes: number | null | undefined): string {
  return holes === 9 ? `${globalId}:all` : `${globalId}:front,${globalId}:back`
}
