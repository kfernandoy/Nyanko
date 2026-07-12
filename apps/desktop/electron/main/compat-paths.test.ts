import { test } from "node:test";
import assert from "node:assert/strict";
import { join } from "node:path";
import { userDataDir, assertUserDataDir, iconPath, LEGACY_APP_ID } from "./compat-paths";

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

// PKG-01: el icono NO viaja en el asar — build/ es el buildResources de
// electron-builder y no se empaqueta. Bajo NSIS la única copia vive en
// resources/icon.png (extraResources, Plan 01). Si esta rama se rompe, la bandeja
// sale VACÍA sin error ni log (nativeImage.createFromPath no lanza) — de ahí el test.

test("iconPath empaquetado apunta al icon.png de resourcesPath", () => {
  const p = iconPath(true, "C:\\Program Files\\Nyanko\\resources", "C:\\cualquiera\\out\\main");
  assert.equal(p, join("C:\\Program Files\\Nyanko\\resources", "icon.png"));
});

test("iconPath en dev apunta al build/icon.png del repo, relativo a mainDir", () => {
  const p = iconPath(false, "C:\\cualquiera\\resources", "E:\\repo\\apps\\desktop\\out\\main");
  assert.equal(p, join("E:\\repo\\apps\\desktop", "build", "icon.png"));
});
