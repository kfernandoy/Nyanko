import { test } from "node:test";
import assert from "node:assert/strict";
import { DECODE_AHEAD, DECODE_BEHIND, decodeWindow, MAX_LIVE_PAGES, pagePairs } from "./readerWindow";

const TECHO_RD_09 = 5;

test("decodeWindow nunca supera el techo de cinco paginas", () => {
  for (let current = 1; current <= 200; current += 1) {
    const indices = decodeWindow(current, 200);
    assert.ok(indices.length <= TECHO_RD_09, `pagina ${current}: ${indices.length} indices vivos`);
    assert.ok(indices.every((indice) => indice >= 1 && indice <= 200));
    assert.equal(new Set(indices).size, indices.length, `pagina ${current}: indices duplicados`);
    assert.deepEqual(indices, [...indices].sort((a, b) => a - b));
  }
});

test("la ventana literal mas menos dos sostiene el techo de RSS", () => {
  // Cinco bitmaps de 24 MB dejan alcanzable el techo de 500 MB; ampliar la
  // ventana a diez paginas suma unos 240 MB y debe poner rojos ambos gates.
  // El +-2 literal de D-07 se afirma constante a constante: MAX_LIVE_PAGES sigue
  // valiendo 5 con DECODE_BEHIND=0 y DECODE_AHEAD=4, y esa ventana asimetrica
  // rompe la lectura hacia atras sin mover el techo de memoria ni un byte.
  assert.equal(DECODE_BEHIND, 2);
  assert.equal(DECODE_AHEAD, 2);
  assert.equal(MAX_LIVE_PAGES, TECHO_RD_09);
  assert.deepEqual(decodeWindow(50, 200), [48, 49, 50, 51, 52]);
});

test("decodeWindow respeta los bordes del capitulo", () => {
  assert.deepEqual(decodeWindow(1, 200), [1, 2, 3]);
  assert.deepEqual(decodeWindow(200, 200), [198, 199, 200]);
  assert.deepEqual(decodeWindow(1, 2), [1, 2]);
});

test("pagePairs aplica el offset de portada y conserva paginas impares", () => {
  assert.deepEqual(pagePairs(6, true, 0), [[1, 2], [3, 4], [5, 6]]);
  assert.deepEqual(pagePairs(6, true, 1), [[1], [2, 3], [4, 5], [6]]);
  assert.deepEqual(pagePairs(5, true, 0), [[1, 2], [3, 4], [5]]);
});
