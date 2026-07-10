import { test } from "node:test";
import assert from "node:assert/strict";
import { userDataDir, assertUserDataDir, LEGACY_APP_ID } from "./compat-paths";

// Self-check DATA-01: prueba el crash-guard de userData bajo Node plano (sin
// electron). Mismo módulo que main/index.ts usa en el arranque: una fuente de
// verdad, una cosa testeada.

test("userDataDir termina en el id heredado", () => {
  const dir = userDataDir("C:\\Users\\x\\AppData\\Roaming");
  assert.ok(dir.endsWith(LEGACY_APP_ID), `esperaba que ${dir} terminara en ${LEGACY_APP_ID}`);
});

test("assertUserDataDir acepta la ruta heredada", () => {
  assert.doesNotThrow(() =>
    assertUserDataDir("C:\\Users\\x\\AppData\\Roaming\\app.nyanko.desktop"),
  );
});

test("assertUserDataDir revienta si userData cae en %APPDATA%\\Nyanko (biblioteca huérfana)", () => {
  assert.throws(() => assertUserDataDir("C:\\Users\\x\\AppData\\Roaming\\Nyanko"));
});
