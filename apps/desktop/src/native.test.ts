import { test } from "node:test";
import assert from "node:assert/strict";
import { native, NATIVE_OPS } from "./native";

// Self-check NATIVE-01 (criterio 3): la frontera nativa no puede driftar en
// silencio. Se afirma simetría en AMBAS direcciones entre `native` y el manifest
// NATIVE_OPS. native.ts mantiene todo acceso a window dentro de cuerpos de función,
// así que importarlo bajo node NO ejecuta esos cuerpos → corre sin DOM.

test("cada op de NATIVE_OPS está mapeada como función en native", () => {
  for (const key of NATIVE_OPS) {
    assert.equal(
      typeof (native as Record<string, unknown>)[key],
      "function",
      key + " no está mapeado en native",
    );
  }
});

test("native y NATIVE_OPS no divergen (sin ops sin registrar)", () => {
  const fnKeys = Object.keys(native).filter(
    (k) => typeof (native as Record<string, unknown>)[k] === "function",
  );
  assert.deepEqual([...fnKeys].sort(), [...NATIVE_OPS].sort(), "native y NATIVE_OPS divergen");
});
