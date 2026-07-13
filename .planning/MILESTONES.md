# Milestones

## v0.2 Tauri → Electron (Shipped: 2026-07-13)

**Phases completed:** 5 phases, 15 plans
**Closeout:** verified_closeout — 5/5 fases `passed`, 12/12 requisitos, audit de milestone `passed`
**Git range:** `18401f3` (spec de diseño, 2026-07-09) → `HEAD` (2026-07-13) · 103 commits · 122 ficheros · +19.540/−9.605
**Releases:** v0.2.0 (migración), v0.2.1, v0.2.2, v0.2.3 (canal vivo hoy)

**Delivered:** el shell de escritorio pasó de Tauri 2 (Rust) a Electron sin que un solo usuario
perdiera su biblioteca — y el parque 0.1.15 ya instalado se migró **solo**, verificando firma.

**Key accomplishments:**

- **El engine-swap no rompió los datos, y está medido.** `userData` queda clavado en
  `%APPDATA%\app.nyanko.desktop` (el identifier de Tauri) con un assert que crashea el arranque si
  resuelve a otra ruta. Tras la migración real: `nyanko.sqlite3` con md5 idéntico, `integrity_check:
  ok`, 2.761 `library_entries` y 25.727 `episodes` — tabla a tabla iguales al backup.

- **El parque 0.1.15 se auto-migró.** Una instalación Tauri real sondeó `latest.json`, verificó la
  firma minisign contra la pubkey horneada en su propio binario y ejecutó el instalador 0.2.0 por su
  cuenta. Que el instalador llegue a arrancar *es* la prueba de la firma: Tauri se niega a ejecutar
  un binario que no verifica.

- **El auto-update se ejercitó de punta a punta, no se escribió.** Una 0.2.0 instalada detectó la
  0.2.1, la descargó **diferencialmente** (766 KB de 128 MB, vía `.blockmap`), verificó su SHA512,
  mató el sidecar, se reinstaló sin asistente y se relanzó sola. Biblioteca intacta, cero
  `nyanko-api.exe` huérfanos.

- **Frontera nativa única.** `src/native.ts` (20 ops) → preload `contextBridge` → `ipcMain.handle` es
  el ÚNICO camino del renderer a lo nativo. Cero `@tauri-apps/*`, cero `src-tauri`, cero Rust en la
  cadena de build. Un self-check bidireccional falla si alguna op queda sin mapear — que es lo que
  mantuvo honesta la migración cuando la Fase 3 dejó 10 stubs.

- **Paridad de features nativas:** tray con toggle de detección, window prefs persistidas
  (close/minimize-to-tray, start-minimized), titlebar frameless, Discord RPC, single-instance,
  autostart, notificaciones, dialog y opener — todo por equivalentes de Electron, con el sidecar
  Python intacto.

- **El audit cruzado encontró lo que ningún gate por fase podía ver (B-1).** El arreglo de la Fase 5
  al problema de bloqueo de ficheros de la Fase 2 había **desactivado en silencio la protección de
  bloqueo de ficheros del propio framework**: `customCheckAppRunning` no es un hook aditivo, es la
  rama `!else` del check de electron-builder. Ambas fases eran, por separado, correctas; el fallo
  vivía en la costura. En máquina rápida el auto-update gana la carrera, y por eso todos los gates
  habían pasado. Arreglado y **probado con la app abierta** antes de cerrar.

**Deuda reconocida (a 0.3):**

- W-3: el menú de bandeja no se entera si pausas la detección desde la UI (estado en una sola
  dirección). Cosmético, se autocorrige al siguiente click.
- D-I-03: `RateLimitedClient(requests_per_minute=90)` mientras AniList responde
  `X-RateLimit-Limit: 30`. No muerde hoy (backfill secuencial), pero una ráfaga comería 429s.
- `docs/extra/RELEASING.md` existe en disco pero `docs/extra/` está gitignorado: el runbook de
  release vive solo en la máquina del autor.
- Los releases v0.2.1 y v0.2.2 se **borraron a propósito** de GitHub tras probar el salto que cada
  uno servía. Sus tags siguen; sus releases dan 404. La evidencia del salto 0.2.0→0.2.1 no es
  reproducible desde el set actual — vive en `05-06-SUMMARY.md`.

---
