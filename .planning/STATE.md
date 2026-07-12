---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
current_phase: 05
current_phase_name: packaging-auto-update
status: phase_complete
stopped_at: Completed 05-06-PLAN.md (PKG-02 cerrado; Fase 5 completa; 0.2.1/0.2.2/0.2.3 publicados)
last_updated: "2026-07-12T21:30:00.000Z"
last_activity: 2026-07-12
last_activity_desc: "05-06 completo: una 0.2.0 instalada se auto-actualizó a 0.2.1 (descarga diferencial + SHA512 + killSidecar + instalación silenciosa). PKG-02 CERRADO"
progress:
  total_phases: 5
  completed_phases: 5
  total_plans: 15
  completed_plans: 15
  percent: 100
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-07-10)

**Core value:** El tracking sigue funcionando idéntico tras cambiar el motor — misma biblioteca, mismos datos, misma detección; solo cambia el shell de Tauri a Electron.
**Current focus:** Phase 05 — packaging-auto-update

## Current Position

Phase: 05 (packaging-auto-update) — **COMPLETE** (6/6 plans)
Status: Fase 5 cerrada. **La migración 0.2 (Tauri → Electron) está completa: 5/5 fases.**
Last activity: 2026-07-12 — 05-06 completo: auto-update real 0.2.0 → 0.2.1 ejecutado y aprobado

**PKG-02 CERRADO — ejecutado, no solo escrito.** Una 0.2.0 instalada detectó la 0.2.1, la descargó
**diferencialmente** (766 KB de 128 MB, gracias al `.blockmap`), verificó su SHA512, ejecutó
`killSidecar()` → `quitAndInstall(true, true)`, se reinstaló **sin asistente** y **se relanzó sola**
como 0.2.1. Biblioteca intacta, cero `nyanko-api.exe` huérfanos. Gate humano aprobado 2026-07-12.

**Releases publicados:** v0.2.0, v0.2.1, v0.2.2, v0.2.3 — los cuatro artefactos cada uno, y ambos
feeds (`latest.yml` de electron-updater + `latest.json` del puente Tauri) verificados contra la red.

**Estado de la máquina de pruebas: M3** — Nyanko **0.2.3** instalada (llegó por auto-update encadenado
desde la 0.2.0), biblioteca intacta con portadas, backfill en ~1,2 min.

**Dos bugs PREEXISTENTES del backend que el update reveló** (ninguno regresión de la Fase 5), ambos
tratados: portadas (D-I-02 — datos reparados, diseño a 0.3) y backfill clavado (arreglado y publicado
como 0.2.2 + 0.2.3). Ver `phases/05-packaging-auto-update/deferred-items.md`.

**Wave order (a ladder, not a fan — see ROADMAP note):**
05-01 (electron-builder + build chain) → 05-05 (packaged icon) → 05-03 (D-02 migration gate)
→ 05-02 (electron-updater) → 05-04 (publish v0.2.0 + Tauri bridge) → 05-06 (real auto-update e2e)

Progress: [██████████] 100%

## Performance Metrics

**Velocity:**

- Total plans completed: 5
- Average duration: — min
- Total execution time: 0.0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 03 | 2 | - | - |
| 4 | 3 | - | - |

**Recent Trend:**

- Last 5 plans: —
- Trend: —

*Updated after each plan completion*
| Phase 03 P01 | 8 | 3 tasks | 6 files |
| Phase 03 P02 | 12 min | 3 tasks | 14 files |
| Phase 04 P01 | 20m | 2 tasks | 6 files |
| Phase 04 P02 | ~15m | 3 tasks | 9 files |
| Phase 04 P03 | ~18m | 2 tasks tasks | 7 files files |
| Phase 05 P01 | 55m | 3 tasks | 7 files |
| Phase 05 P05 | ~12 min | 1 tasks | 4 files |
| Phase 05 P03 | ~35 min | 2 tasks | 1 files |
| Phase 05 P02 | ~35 min | 3 tasks | 6 files |
| Phase 05 P04 | ~75 min | 3 tasks | 4 files |
| Phase 05 P06 | ~4 h | 2 tasks | 6 files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- Migración a Electron sobre seguir en Tauri (madurez de ecosistema desktop).
- electron-vite (no Electron a mano) por HMR main/preload/renderer + integración builder.
- `src/native.ts` como frontera nativa única; `userData` fijo a `app.nyanko.desktop`.
- [Phase ?]: native.ts wired ops keep web/dev fallbacks; window-control + updater stubs throw, autostart/prefs/discord stubs are safe no-ops
- [Phase ?]: Phase 03: every renderer consumer imports native.ts only; @tauri-apps deps + tauri script removed; repo builds Rust-free
- [Phase ?]: 04-01: single 256x256 brand icon at build/icon.png (D-07) reused by tray + Phase 5
- [Phase ?]: 04-01: titlebar render gate flipped HAS_TAURI -> isNative; JSX/styles verbatim (D-04)
- [Phase ?]: 04-02: window_prefs.json at userData, no migration (D-05); set payload coerced to 3 booleans + userData-scoped write (T-04-04/05); tray labels keep accented 'detección' per Rust parity (D-08); window-prefs core electron-free for test:prefs
- [Phase ?]: 04-03: T-04-SC gate approved by user before installing @xhayper/discord-rpc@1.3.4; Discord RP lazy-connects + silent no-op (D-02/D-03) plus a no-op error listener to prevent an EventEmitter main-process crash; single-instance = requestSingleInstanceLock + focus; autostart = app.setLoginItemSettings(args:['--minimized'])
- [Phase ?]: 05-05: iconPath() recibe isPackaged/resourcesPath como parametros: compat-paths.ts sigue Electron-free y self-checkable bajo Node plano; el icono empaquetado se lee de resources/icon.png (extraResources del Plan 01), no de build/
- [Phase 05]: 05-03 / D-02 RESUELTO POR EXPERIMENTO (2026-07-12, instalación 0.1.15 real): el `uninstall.exe /S` de Tauri **NO** borra `%APPDATA%\app.nyanko.desktop` (DB idéntica byte a byte, md5 51cb246b…). → se cablea la **rama A** (desinstalar Tauri en silencio en `customInit`); la **rama B no existe en el árbol** y `electron-builder.yml` no se toca (sin `nsis.guid`, electron-builder deriva su GUID del appId — no compartimos clave con Tauri, hacemos que Tauri desaparezca)
- [Phase 05]: 05-03: la clave de desinstalación de Tauri es `HKCU\...\Uninstall\Nyanko` (un NOMBRE, no un GUID entre llaves) y sus valores vienen **entrecomillados dentro del propio dato** → hay que des-entrecomillarlos antes de usarlos como ruta
- [Phase 05]: 05-03: el `ExecWait` usa `_?=<InstallLocation>` (desinstalación síncrona real) + remate `Delete`/`RMDir /r`. No es por el directorio: es porque Tauri y electron-builder crean el MISMO `$SMPROGRAMS\Nyanko.lnk`, y sin `_?=` el uninstaller rezagado (retorna en 2,5 s, sigue borrando detrás) se lleva por delante el acceso directo recién creado. No "simplificar" a un ExecWait pelado
- [Phase 05]: 05-03: exe de Tauri = `nyanko-desktop.exe`, exe de Electron = `Nyanko.exe` — nombres DISTINTOS: instalar encima no habría pisado nada (esto es lo que habría roto la rama B)
- [Phase 05]: 05-03 (verificación humana): el icono en bandeja de la 0.2.0 empaquetada cierra el hueco que 05-05 dejó abierto a propósito (su rama `isPackaged` no era ejecutable en dev)
- [Phase 05]: El feed del updater vive en app-update.yml dentro del paquete, nunca en codigo — T-05-04: si el origen fuese configurable desde el main o el renderer, un renderer comprometido podria apuntar el updater a un exe arbitrario
- [Phase 05]: El bloque files: del asar usa exclusiones negativas, no una whitelist — Reescribir la lista de lo que SI entra en el paquete es lo que rompe paquetes; sacar lo que sobra (!.claude, !.env*) es el diff minimo
- [Phase 05]: 05-04 / **el `browser_download_url` de un asset en un release BORRADOR es PROVISIONAL** (`…/download/untagged-<hash>/…`) y **muere en 404 al publicar**. Meterlo en `latest.json` publica un puente correctamente firmado apuntando a un enlace muerto → TODO el parque 0.1.15 varado, sin ningún error visible (T-05-12). La URL se compone del **tag** + el **nombre del asset firmado** que devuelve la API
- [Phase 05]: 05-04: **GitHub permite varios BORRADORES con el mismo `tag_name`** (el tag no es real hasta publicar). Un publish fallido a medias deja un huérfano y `releases.find()` coge «el primero» — azar sobre a cuál se le sube la firma. El puente exige que haya exactamente UNO
- [Phase 05]: 05-04: `npx` es un `.cmd` → `shell: true` obligatorio (CVE-2024-27980) → un argumento **vacío** (`""`) se evapora al reconstruir la línea de comandos. Usar `--password=` (la forma que el RELEASING.md de la era Tauri ya documentaba)
- [Phase 05]: 05-04: **el desinstalador de electron-builder IGNORA `/S`** y abre su asistente, incluso con la `QuietUninstallString` que publica el propio registro. Cualquier automatización que cuente con un uninstall silencioso se colgará ahí (a los usuarios no les afecta: nadie desinstala en el camino de D-01)
- [Phase 05]: 05-04: la md5 de `nyanko.sqlite3` **cambia con el uso** (SQLite reescribe páginas in situ, el tamaño no se mueve). Como invariante de «no se ha perdido la biblioteca» solo vale entre pasos en los que la app NO corre; el invariante bueno son los **conteos por tabla**
- [Phase 05]: 05-04 / D-01 PROBADO: una instalación 0.1.15 real arrancó, sondeó `latest.json`, verificó la firma minisign y ejecutó el instalador 0.2.0 SOLA. Que el instalador llegue a arrancar ES la prueba de la firma (Tauri se niega a ejecutar un binario que no verifica)
- [Phase 05]: 05-06 / **PKG-02 PROBADO**: una 0.2.0 instalada detectó la 0.2.1, la descargó, verificó SHA512, mató su sidecar (`killSidecar()` → `quitAndInstall(true,true)`), se reinstaló SIN asistente y se relanzó sola. Biblioteca intacta, cero sidecars huérfanos. Gate humano aprobado
- [Phase 05]: 05-06: **el auto-update es DIFERENCIAL** — el `.blockmap` no es un asset de adorno: `main.log` mide `Full: 128,125.5 KB, To download: 766.47 KB (1%)`. Un update de 128 MB cuesta 766 KB
- [Phase 05]: 05-06 / **CORRIGE AL 05-04**: los DOS BORRADORES con el mismo tag NO vienen de un publish fallido a medias (ese diagnóstico era FALSO). **electron-builder lanza sus publishers en PARALELO**: ambos comprueban «¿existe el release?» antes de que ninguno lo haya creado, y ambos lo crean (`creating GitHub release reason=release doesn't exist` dos veces en su propio log). Reproducido 3 de 3 en publicaciones limpias a la primera (0.2.1, 0.2.2, 0.2.3). La guarda del `publish-bridge` («exactamente UNO o aborta») protege del caso NORMAL, no de uno raro
- [Phase 05]: 05-06: ni las portadas rotas ni el backfill clavado eran regresiones de la Fase 5 — son bugs PREEXISTENTES del backend que el reinicio del sidecar (inherente a todo update) se limitó a REVELAR
- [Phase 05]: 05-06: **el timeout del cliente y el coste de la query son UN solo invariante**. El backfill no cambió: **AniList se degradó ~6x** (la misma query que su propio comentario mide en ~3,5 s tarda hoy 17-25 s) y el timeout de 15 s dejó de caber → todos los lotes expiraban y la barra se quedaba en 0/1811 **sin un solo error visible**. Arreglado pidiendo solo lo que la grid pinta (~13 min → ~1,2 min), publicado como 0.2.2 y 0.2.3

### Pending Todos

None yet.

### Blockers/Concerns

- **Data dir (crítico):** si `userData` no se fija antes del primer acceso a paths, Electron usaría `%APPDATA%\Nyanko` y la biblioteca existente quedaría huérfana. Mitigado por assert de arranque en Phase 1.
- **Sidecar en frío:** conservar el gate de readiness (`waitForBackend` + wait del `port` file) para no reintroducir el "Cargando biblioteca ~1min". Cubierto en Phase 2.

## Deferred Items

Items acknowledged and carried forward from previous milestone close:

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| Backend (0.3) | **D-I-02** — el backend persiste URLs de assets con el `host:puerto` dentro; si el sidecar cambia de puerto, la biblioteca se queda sin portadas de forma permanente y silenciosa. Datos reparados (3.874 URLs); el fallo de diseño sigue vivo | Deferred | 05-06 |
| Backend (0.3) | **D-I-03** — `RateLimitedClient(requests_per_minute=90)` pero AniList reporta hoy `X-RateLimit-Limit: 30`. No muerde ahora (backfill secuencial, ~1 req/2 s) pero una ráfaga comería 429s | Deferred | 05-06 |

Detalle completo en `phases/05-packaging-auto-update/deferred-items.md`.

## Session Continuity

Last session: 2026-07-12T21:30:00.000Z
Stopped at: Completed 05-06-PLAN.md — **Fase 5 completa (6/6) y con ella la migración 0.2 entera (5/5 fases)**. PKG-02 cerrado con evidencia. Siguiente: cierre de milestone
Resume file: None
