#!/usr/bin/env node
// D-01 — El puente de un solo uso hacia Electron.
//
// El parque instalado corre Tauri 0.1.15, que sondea
// releases/latest/download/latest.json y verifica una firma minisign contra la
// pubkey horneada en su propio binario. El updater de Tauri NO sabe qué
// framework generó el NSIS que descarga: si la firma verifica, lo ejecuta.
// Por eso basta con firmar el instalador de electron-builder con LA MISMA clave
// y publicar un último latest.json junto al latest.yml (D-08).
//
// Si se publicara solo latest.yml, cada instalación 0.1.15 del mundo seguiría
// sondeando latest.json, no vería nunca una versión nueva, y quedaría varada
// para siempre — sin ningún error visible ni para el usuario ni para nosotros.
//
// Se ejecuta DESPUÉS de `electron-builder --publish always`, que ya ha subido
// el .exe y el latest.yml a un release BORRADOR. Este script añade el .sig y el
// latest.json a ESE MISMO borrador: así el release se publica con los cuatro
// artefactos ya dentro y nunca hay una ventana en la que
// releases/latest/download/latest.json devuelva 404 al parque 0.1.15 (T-05-14).
//
// Uso:  GH_TOKEN=... node apps/desktop/scripts/publish-bridge.mjs "release notes"

import { createHash, createPublicKey, verify as edVerify } from "node:crypto";
import { execFileSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { homedir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

// ---------------------------------------------------------------------------
// EL ANCLA DE CONFIANZA (T-05-11)
// ---------------------------------------------------------------------------
// Este es, byte a byte, el string que 0.1.15 lleva horneado en
// tauri.conf.json → plugins.updater.pubkey (a50659c^). Está aquí LITERAL y no se
// lee del disco a propósito: es lo único que permite detectar que se ha firmado
// con otra clave. Firmar con la clave equivocada es el fallo irrecuperable —
// vara a todo el parque instalado y no se nota hasta que un usuario se queja.
export const EMBEDDED_PUBKEY_B64 =
  "dW50cnVzdGVkIGNvbW1lbnQ6IG1pbmlzaWduIHB1YmxpYyBrZXk6IEJBQ0FCNjk0NzAyOEY2RDQKUldUVTlpaHdsTGJLdW9vN3A3MHVBaGtzNVloMlcrSnVOckNWbVQyVXRjV2N3c0JSdURYbVM4YUEK";

const REPO = "kfernandoy/Nyanko";
// Versión PINEADA (T-05-SC-2). Nunca @latest: un `latest` comprometido correría
// con acceso a la clave privada que autoriza los binarios de todo el parque.
const SIGNER_PKG = "@tauri-apps/cli@2.8.4";
const PRIVATE_KEY = join(homedir(), ".tauri", "nyanko-updater.key");

// ===========================================================================
// Helpers puros (los que testea publish-bridge.test.mjs)
// ===========================================================================

// Prefijo DER de una SubjectPublicKeyInfo Ed25519: envolviendo los 32 bytes
// crudos con esto, node:crypto los acepta sin dependencias externas.
const SPKI_ED25519_PREFIX = Buffer.from("302a300506032b6570032100", "hex");

/** El .pub de Tauri es base64 del fichero .pub de minisign (2 líneas). La 2ª,
 *  decodificada, son 42 bytes: 2 de algoritmo, 8 de key id, 32 de clave. */
export function parseMinisignKey(pubB64) {
  const lines = Buffer.from(pubB64.trim(), "base64").toString("utf8").trim().split(/\r?\n/);
  if (lines.length < 2) throw new Error("malformed minisign public key: expected 2 lines");
  const raw = Buffer.from(lines[1].trim(), "base64");
  if (raw.length !== 42) throw new Error(`malformed minisign public key: expected 42 bytes, got ${raw.length}`);
  return {
    algorithm: raw.subarray(0, 2).toString("utf8"),
    keyId: raw.subarray(2, 10).toString("hex"),
    publicKey: raw.subarray(10, 42),
  };
}

/** El .sig de Tauri es base64 del fichero .sig de minisign (4 líneas). La 2ª,
 *  decodificada, son 74 bytes: 2 de algoritmo, 8 de key id, 64 de firma.
 *  Algoritmo: "Ed" = legacy (firma el contenido) · "ED" = prehashed (firma el
 *  BLAKE2b-512 del contenido). */
export function parseMinisignSig(sigB64) {
  const lines = Buffer.from(sigB64.trim(), "base64").toString("utf8").trim().split(/\r?\n/);
  if (lines.length < 2) throw new Error("malformed minisign signature: expected at least 2 lines");
  const raw = Buffer.from(lines[1].trim(), "base64");
  if (raw.length !== 74) throw new Error(`malformed minisign signature: expected 74 bytes, got ${raw.length}`);
  return {
    algorithm: raw.subarray(0, 2).toString("utf8"),
    keyId: raw.subarray(2, 10).toString("hex"),
    signature: raw.subarray(10, 74),
  };
}

/** Verifica en Ed25519 la firma minisign de `fileBytes` contra `pubB64`.
 *  ponytail: no verifica la firma GLOBAL del trusted comment. Lo que autoriza a
 *  ejecutar el binario es la firma del payload; la global solo ata un comentario
 *  al lado. Verificar la del payload es exactamente lo que hace 0.1.15 al
 *  decidir si ejecuta lo que ha descargado. */
export function verifyMinisign(fileBytes, sigB64, pubB64) {
  const key = parseMinisignKey(pubB64);
  const sig = parseMinisignSig(sigB64);

  // Key id distinto = firmado con OTRA clave. Es el caso que hay que cazar.
  if (key.keyId !== sig.keyId) return false;

  const message =
    sig.algorithm === "ED"
      ? createHash("blake2b512").update(fileBytes).digest() // prehashed
      : fileBytes; // "Ed", legacy: se firma el contenido

  const spki = createPublicKey({
    key: Buffer.concat([SPKI_ED25519_PREFIX, key.publicKey]),
    format: "der",
    type: "spki",
  });
  return edVerify(null, message, spki, sig.signature);
}

/** El esquema EXACTO que el updater de Tauri 0.1.15 espera (RELEASING.md:43-55).
 *  `signature` es el CONTENIDO del fichero .sig — no una ruta y no un hash. Es
 *  el error clásico de este flujo. */
export function buildLatestJson({ version, notes, signature, url, pubDate = new Date().toISOString() }) {
  return {
    version,
    notes,
    pub_date: pubDate,
    platforms: {
      "windows-x86_64": { signature, url },
    },
  };
}

// ===========================================================================
// Efectos — cada guarda aborta ANTES de subir nada
// ===========================================================================

function fail(msg) {
  console.error(`\n  ABORT: ${msg}\n`);
  process.exit(1);
}

async function gh(token, url, init = {}) {
  const res = await fetch(url, {
    ...init,
    headers: {
      Authorization: `Bearer ${token}`, // T-05-13: el token solo vive aquí. Nunca se imprime.
      Accept: "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
      ...(init.headers ?? {}),
    },
  });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`GitHub ${init.method ?? "GET"} ${url.replace(/\?.*/, "")} → ${res.status}: ${body.slice(0, 300)}`);
  }
  return res.status === 204 ? null : res.json();
}

async function uploadAsset(token, release, name, contentType, body) {
  // Idempotencia: si re-ejecutamos el puente, el asset viejo estorba.
  const existing = release.assets.find((a) => a.name === name);
  if (existing) {
    await gh(token, `https://api.github.com/repos/${REPO}/releases/assets/${existing.id}`, { method: "DELETE" });
    console.log(`  · removed stale asset ${name}`);
  }
  const uploadUrl = release.upload_url.replace(/\{.*\}$/, "");
  const asset = await gh(token, `${uploadUrl}?name=${encodeURIComponent(name)}`, {
    method: "POST",
    headers: { "Content-Type": contentType },
    body,
  });
  console.log(`  · uploaded ${name} (${asset.size} B)`);
}

async function main() {
  const here = dirname(fileURLToPath(import.meta.url));
  const desktopDir = join(here, "..");
  const { version } = JSON.parse(readFileSync(join(desktopDir, "package.json"), "utf8"));
  const notes = process.argv[2] ?? `Nyanko ${version}`;

  // 1. GH_TOKEN
  const token = process.env.GH_TOKEN;
  if (!token) fail("GH_TOKEN is not set. See docs/extra/RELEASING.md.");

  // 2. El instalador que electron-builder acaba de subir
  const exeName = `Nyanko-Setup-${version}.exe`;
  const exePath = join(desktopDir, "release", exeName);
  if (!existsSync(exePath)) fail(`${exePath} not found. Run \`npm run dist:publish --workspace @nyanko/desktop\` first.`);

  // 3. ¿Es LA clave? (T-05-11a) La pubkey del disco tiene que ser idéntica al
  //    ancla horneada en los binarios 0.1.15. Si no, estaríamos a punto de
  //    firmar con una clave que nadie en el campo puede verificar.
  const pubPath = `${PRIVATE_KEY}.pub`;
  if (!existsSync(pubPath)) fail(`${pubPath} not found. The 0.1.15 install base cannot be reached without this key.`);
  if (readFileSync(pubPath, "utf8").trim() !== EMBEDDED_PUBKEY_B64.trim()) {
    fail(
      "the public key on disk does NOT match the key baked into the 0.1.15 binaries.\n" +
        "  Signing with it would strand every installed user, silently and forever.",
    );
  }
  console.log(`✓ signing key matches the pubkey baked into 0.1.15 (${parseMinisignKey(EMBEDDED_PUBKEY_B64).keyId})`);

  // 4. Firmar. Se invoca por npx con la versión PINEADA — @tauri-apps/cli NO
  //    vuelve a package.json (SHELL-02: el repo se queda Tauri-free).
  console.log(`… signing ${exeName} with ${SIGNER_PKG}`);
  execFileSync("npx", ["--yes", SIGNER_PKG, "signer", "sign", "-f", PRIVATE_KEY, "--password", "", exePath], {
    stdio: ["ignore", "inherit", "inherit"], // la clave se pasa por RUTA; su contenido nunca se vuelca (T-05-13)
    shell: process.platform === "win32",
  });

  const sigPath = `${exePath}.sig`;
  if (!existsSync(sigPath)) fail(`the signer did not produce ${sigPath}.`);
  const signature = readFileSync(sigPath, "utf8").trim();

  // 5. VERIFICAR LA FIRMA RECIÉN CREADA (T-05-11b). Una firma mala es
  //    indistinguible de una buena hasta que falla, en silencio, en cada
  //    cliente instalado. Si no verifica, no se sube NADA.
  if (!verifyMinisign(readFileSync(exePath), signature, EMBEDDED_PUBKEY_B64)) {
    fail("the freshly created signature does NOT verify against the 0.1.15 pubkey. Nothing was uploaded.");
  }
  console.log(`✓ signature verifies against the 0.1.15 pubkey — 0.1.15 clients will accept this installer`);

  // 6. Localizar el release borrador. /releases (autenticado) SÍ devuelve los
  //    borradores; /releases/tags/... no.
  const tag = `v${version}`;
  const releases = await gh(token, `https://api.github.com/repos/${REPO}/releases?per_page=100`);
  const release = releases.find((r) => r.tag_name === tag);
  if (!release) fail(`no release tagged ${tag} in ${REPO}. Run \`npm run dist:publish\` first.`);

  const exeAsset = release.assets.find((a) => a.name === exeName);
  if (!exeAsset) fail(`release ${tag} has no asset named ${exeName}. electron-builder did not upload the installer.`);

  // 7. Subir. La url del latest.json sale del browser_download_url que devuelve
  //    la API para el asset que ACABAMOS de firmar — no se compone a mano
  //    (T-05-12: firmar un fichero y apuntar a otro es indetectable hasta que
  //    falla en el cliente).
  const latestJson = buildLatestJson({ version, notes, signature, url: exeAsset.browser_download_url });
  await uploadAsset(token, release, `${exeName}.sig`, "application/octet-stream", signature);
  await uploadAsset(token, release, "latest.json", "application/json", JSON.stringify(latestJson, null, 2));

  // 8. Resumen
  const fresh = await gh(token, `https://api.github.com/repos/${REPO}/releases/${release.id}`);
  console.log(`\n  Release ${tag} (${fresh.draft ? "DRAFT" : "published"}) — assets:`);
  for (const a of fresh.assets) console.log(`    - ${a.name}`);
  console.log(`\n  latest.json → ${exeAsset.browser_download_url}`);
  if (fresh.draft) {
    console.log(`\n  NEXT: publish the draft on GitHub. A draft does NOT resolve through`);
    console.log(`  releases/latest/download/... — the 0.1.15 install base would see nothing.\n`);
  }
}

// Solo corre como script; importarlo desde el test no dispara nada.
if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  main().catch((err) => fail(err.message));
}
