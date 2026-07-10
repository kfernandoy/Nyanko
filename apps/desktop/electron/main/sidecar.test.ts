import { test } from "node:test";
import assert from "node:assert/strict";
import { parsePortFile, isDevMode, healthUrl, resolveSidecarExe } from "./sidecar";

// Self-check NATIVE-02: ejerce SOLO los helpers puros bajo Node plano (sin
// electron, sin spawn/taskkill/net). Misma disciplina que compat-paths.test.ts.

test("parsePortFile lee texto plano y devuelve el número (mirror instance.py)", () => {
  assert.equal(parsePortFile("8765\n"), 8765);
});

test("parsePortFile devuelve null en contenido inválido", () => {
  assert.equal(parsePortFile("nope"), null);
});

test("parsePortFile devuelve null en cadena vacía", () => {
  assert.equal(parsePortFile(""), null);
});

test("isDevMode: dev cuando NO está empaquetado (D-10)", () => {
  assert.equal(isDevMode(false), true);
  assert.equal(isDevMode(true), false);
});

test("healthUrl construye el endpoint de readiness contra 127.0.0.1 (D-03)", () => {
  assert.equal(healthUrl(8765), "http://127.0.0.1:8765/api/health");
});

test("resolveSidecarExe honra el override NYANKO_SIDECAR_EXE", () => {
  const prev = process.env.NYANKO_SIDECAR_EXE;
  process.env.NYANKO_SIDECAR_EXE = "C:\\custom\\nyanko-api.exe";
  try {
    assert.equal(resolveSidecarExe(), "C:\\custom\\nyanko-api.exe");
  } finally {
    if (prev === undefined) delete process.env.NYANKO_SIDECAR_EXE;
    else process.env.NYANKO_SIDECAR_EXE = prev;
  }
});
