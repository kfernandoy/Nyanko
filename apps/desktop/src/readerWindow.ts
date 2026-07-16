// Este modulo queda separado del componente para que el plan 07 pueda probarlo sin DOM
// y para que el techo de memoria sea una propiedad demostrable del codigo, no una intencion.
export const DECODE_BEHIND = 2;
export const DECODE_AHEAD = 2;
export const MAX_LIVE_PAGES = DECODE_BEHIND + 1 + DECODE_AHEAD;

export function decodeWindow(current: number, total: number): number[] {
  const pageTotal = Number.isFinite(total) ? Math.max(0, Math.floor(total)) : 0;
  if (pageTotal === 0) return [];
  if (pageTotal <= MAX_LIVE_PAGES) {
    return Array.from({ length: pageTotal }, (_, index) => index + 1);
  }

  const currentPage = Number.isFinite(current)
    ? Math.min(pageTotal, Math.max(1, Math.floor(current)))
    : 1;
  const first = Math.max(1, currentPage - DECODE_BEHIND);
  const last = Math.min(pageTotal, currentPage + DECODE_AHEAD);
  return Array.from({ length: last - first + 1 }, (_, index) => first + index);
}

export function pagePairs(total: number, doublePage: boolean, offset: number): number[][] {
  const pageTotal = Number.isFinite(total) ? Math.max(0, Math.floor(total)) : 0;
  const pages = Array.from({ length: pageTotal }, (_, index) => index + 1);
  if (!doublePage) return pages.map((page) => [page]);

  // El offset es manual: adivinarlo por la relacion de aspecto falla justo en las paginas
  // dobles reales, y un emparejamiento incorrecto vuelve inutilizable el lector.
  const pairs: number[][] = offset === 1 && pages.length > 0 ? [[pages.shift()!]] : [];
  while (pages.length > 0) pairs.push(pages.splice(0, 2));
  return pairs;
}
