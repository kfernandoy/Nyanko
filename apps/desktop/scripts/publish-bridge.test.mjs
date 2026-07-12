// Self-check de los helpers puros del puente D-01. Node plano, cero deps.
//
// Lo que de verdad se prueba aquí es que verifyMinisign() SABE DECIR QUE NO:
// una firma mala es indistinguible de una buena hasta que falla, en silencio, en
// cada cliente 0.1.15 instalado. Un verificador que siempre dice `true` pasaría
// desapercibido y dejaría pasar exactamente el fallo que existe para atrapar.

import test from "node:test";
import assert from "node:assert/strict";
import { createHash, generateKeyPairSync, sign as edSign } from "node:crypto";

import {
  EMBEDDED_PUBKEY_B64,
  buildLatestJson,
  parseMinisignKey,
  verifyMinisign,
} from "./publish-bridge.mjs";

/** Compone un par .pub/.sig minisign REALES (prehashed, "ED") sobre `payload`. */
function fakeMinisign(payload, { keyId = Buffer.from("0011223344556677", "hex") } = {}) {
  const { publicKey, privateKey } = generateKeyPairSync("ed25519");
  // Los 32 bytes crudos son la cola de la SPKI DER (12 bytes de prefijo).
  const rawPub = publicKey.export({ format: "der", type: "spki" }).subarray(12);

  const pubLine = Buffer.concat([Buffer.from("Ed"), keyId, rawPub]).toString("base64");
  const pubFile = `untrusted comment: minisign public key\n${pubLine}\n`;

  const digest = createHash("blake2b512").update(payload).digest();
  const rawSig = edSign(null, digest, privateKey);
  const sigLine = Buffer.concat([Buffer.from("ED"), keyId, rawSig]).toString("base64");
  const sigFile = `untrusted comment: signature\n${sigLine}\ntrusted comment: timestamp:0\nAAAA\n`;

  return {
    pubB64: Buffer.from(pubFile).toString("base64"),
    sigB64: Buffer.from(sigFile).toString("base64"),
  };
}

test("verifyMinisign acepta una firma buena (prehashed)", () => {
  const payload = Buffer.from("pretend this is Nyanko-Setup-0.2.0.exe");
  const { pubB64, sigB64 } = fakeMinisign(payload);
  assert.equal(verifyMinisign(payload, sigB64, pubB64), true);
});

test("verifyMinisign rechaza un payload alterado en UN byte", () => {
  const payload = Buffer.from("pretend this is Nyanko-Setup-0.2.0.exe");
  const { pubB64, sigB64 } = fakeMinisign(payload);

  const tampered = Buffer.from(payload);
  tampered[0] ^= 0x01;
  assert.equal(verifyMinisign(tampered, sigB64, pubB64), false);
});

test("verifyMinisign rechaza una firma de OTRA clave (key id distinto)", () => {
  const payload = Buffer.from("pretend this is Nyanko-Setup-0.2.0.exe");
  const { pubB64 } = fakeMinisign(payload);
  // Mismo payload, firmado por otro par con otro key id: es el escenario de
  // "firmado con la clave equivocada", el fallo irrecuperable de D-01.
  const { sigB64: otherSig } = fakeMinisign(payload, { keyId: Buffer.from("aabbccddeeff0011", "hex") });
  assert.equal(verifyMinisign(payload, otherSig, pubB64), false);
});

test("buildLatestJson produce el esquema que espera el updater de Tauri", () => {
  const json = buildLatestJson({
    version: "0.2.0",
    notes: "Engine swap to Electron.",
    signature: "SIG_FILE_CONTENTS",
    url: "https://github.com/kfernandoy/Nyanko/releases/download/v0.2.0/Nyanko-Setup-0.2.0.exe",
    pubDate: "2026-07-12T00:00:00.000Z",
  });

  assert.deepEqual(Object.keys(json), ["version", "notes", "pub_date", "platforms"]);
  const win = json.platforms["windows-x86_64"];
  // El error clásico: meter una ruta o un hash en vez del CONTENIDO del .sig.
  assert.equal(win.signature, "SIG_FILE_CONTENTS");
  assert.match(win.url, /Nyanko-Setup-0\.2\.0\.exe$/);
});

test("EMBEDDED_PUBKEY_B64 es un fichero de clave pública minisign de 2 líneas", () => {
  const decoded = Buffer.from(EMBEDDED_PUBKEY_B64, "base64").toString("utf8").trim();
  const lines = decoded.split(/\r?\n/);
  assert.equal(lines.length, 2);
  assert.match(lines[0], /^untrusted comment: minisign public key/);

  const key = parseMinisignKey(EMBEDDED_PUBKEY_B64);
  assert.equal(key.algorithm, "Ed");
  assert.equal(key.publicKey.length, 32);
  // El key id del parque instalado. minisign lo guarda en little-endian y lo
  // MUESTRA al revés: el comentario dice BACAB6947028F6D4, los bytes son estos.
  assert.equal(key.keyId, "d4f6287094b6caba");
});
