# Phase 5: Packaging + auto-update - Context

**Gathered:** 2026-07-11
**Status:** Ready for planning

<domain>
## Phase Boundary

Nyanko se distribuye como instalador Windows NSIS (producido por electron-builder) que
incluye el sidecar Python y los bundles de extensión, y se auto-actualiza desde GitHub
Releases vía electron-updater. Cierra la paridad con el flujo de release de Tauri y es la
última fase del engine-swap 0.2.

**Requisitos:** PKG-01, PKG-02.

**Fuera de alcance:** firma de código con certificado real (v2/deferred), CI en GitHub
Actions, cualquier feature de producto (0.2 es engine-swap puro).

</domain>

<decisions>
## Implementation Decisions

### Migración de los usuarios existentes (0.1.15 Tauri → 0.2.0 Electron)

- **D-01:** **Auto-migración firmada.** Los usuarios en producción corren Tauri 0.1.15, que
  sondea `https://github.com/kfernandoy/Nyanko/releases/latest/download/latest.json` y
  verifica la firma minisign contra la pubkey embebida en su binario. El updater de Tauri
  baja el instalador NSIS, verifica la firma y lo ejecuta — **no le importa qué framework
  generó ese NSIS**. Por lo tanto: se firma el instalador de electron-builder con la MISMA
  clave minisign (`$USERPROFILE\.tauri\nyanko-updater.key`, password vacía) y se publica un
  último `latest.json`. Los de 0.1.15 se auto-actualizan y aterrizan en Electron sin
  intervención. De ahí en adelante manda electron-updater (`latest.yml` + SHA512).
  No romper este puente: si solo se publicara `latest.yml`, todo 0.1.15 quedaría varado
  para siempre — nunca vería una versión nueva.

- **D-02:** **Desinstalar la app Tauri vieja con un uninstall silencioso, PERO detrás de una
  verificación empírica bloqueante.** El desinstalador NSIS de Tauri ofrece borrar los datos
  de la aplicación, y esos datos son `%APPDATA%\app.nyanko.desktop` — la biblioteca entera
  del usuario. Antes de cablear `uninstall.exe /S` en el hook de preinstalación hay que
  **probar en una instalación real que el modo silencioso NO borra `%APPDATA%`**.
  - Si NO la borra → hook preinstall corre el uninstaller de Tauri en silencio.
  - Si la borra → **caer a "instalar encima"**: apuntar el NSIS de Electron al mismo
    directorio de instalación y la misma clave de desinstalación que usaba Tauri, sin correr
    ningún uninstaller. Una sola entrada en Agregar/quitar programas, cero riesgo de datos.
  Esta verificación es un gate, no un supuesto. La pérdida de biblioteca es el peor
  resultado posible de esta fase y DATA-01 existe precisamente para evitarla.

### Instalador

- **D-03:** **NSIS asistido, per-user.** `oneClick: false` + selector de idioma español/inglés
  (`installerLanguages`, `displayLanguageSelector`) + EULA — paridad con lo que los usuarios
  ya conocen de Tauri. Per-user (sin UAC): encaja con una app gratuita de comunidad y no
  rompe el update silencioso (per-machine pediría UAC en cada auto-update).

- **D-04:** **Updates silenciosos igual.** `quitAndInstall(isSilent = true)` funciona con un
  instalador asistido: primera instalación con wizard, updates sin wizard. No hay que elegir
  entre paridad y updates silenciosos — se pueden tener los dos.

- **D-05:** **Hook preinstall que mata el sidecar.** El `installer-hooks.nsh` de Tauri hacía
  `taskkill /F /IM nyanko-api.exe /T` en `NSIS_HOOK_PREINSTALL` porque el sidecar sobrevive al
  updater y mantiene bloqueados `_internal\*` y el propio exe, haciendo fallar el copiado.
  electron-builder acepta un `include` custom `.nsh` — replicar ese taskkill. Además,
  `killSidecar()` ya existe en `electron/main/index.ts` y su comentario dice explícitamente
  que "el updater de Phase 5 llama esta MISMA killSidecar antes de quitAndInstall": llamarla,
  no duplicarla. Los dos mecanismos son complementarios (uno cubre el proceso propio, el otro
  cualquier huérfano).

### Layout de recursos

- **D-06:** **La extensión va AL LADO del exe del sidecar, no en la raíz de recursos.** El
  backend resuelve la carpeta en `main.py:2924`:
  ```python
  if getattr(sys, "frozen", False):
      dist = Path(sys.executable).parent / "extension"
  ```
  Como `resolveSidecarExe()` (`electron/main/sidecar.ts:38`) pone el exe en
  `process.resourcesPath/nyanko-api/nyanko-api.exe`, los bundles DEBEN copiarse a
  `resources/nyanko-api/extension/{chromium,firefox}`. Ponerlos en `resources/extension/`
  (el layout obvio, calcado de Tauri) hace que `/api/extension/bundle` devuelva `null` y el
  botón "abrir carpeta de la extensión" quede muerto en producción, sin error visible.
  El sidecar Python NO se toca — 0.2 es engine-swap puro (restricción de milestone).

- **D-07:** **extraResources:**
  - `apps/backend/dist/nyanko-api/` → `resources/nyanko-api/` (PyInstaller onedir ya produce
    `nyanko-api.exe` + `_internal/` con esa forma exacta — encaja con `resolveSidecarExe()`
    sin tocar código).
  - `apps/extension/dist/chromium` → `resources/nyanko-api/extension/chromium`
  - `apps/extension/dist/firefox` → `resources/nyanko-api/extension/firefox`

### Publicación

- **D-08:** **electron-builder publica, un script aparte tiende el puente.**
  `electron-builder --publish` sube el NSIS y genera/sube `latest.yml` con el SHA512 y el
  tamaño correctos **por construcción**. Escribir `latest.yml` a mano (como se hacía con
  `latest.json`) es frágil: un SHA512 mal copiado rompe el update de todos los usuarios en
  silencio y no se detecta hasta que falla en el cliente. Solo necesita `GH_TOKEN` en el
  entorno — no requiere el CLI `gh` (que no está instalado).
  El puente de D-01 (firmar con minisign + subir `latest.json`) queda como paso scripteado
  aparte, porque electron-builder no sabe de minisign.
  Sigue siendo un build local — sin CI.

### Claude's Discretion

- **Icono en el paquete** (el riesgo diferido que dejó la Fase 4): hoy `index.ts:40` y
  `tray.ts:69` resuelven `join(__dirname, "../../build/icon.png")`, y `build/` es el
  `buildResources` dir de electron-builder — **no se empaqueta dentro de la app**. Sin
  arreglarlo, la bandeja sale sin icono en el NSIS. Se resuelve reusando el patrón que
  `resolveSidecarExe()` ya establece (override/`process.resourcesPath` con fallback a dev):
  `extraResources` copia el icono a `resources/icon.png` y la resolución se bifurca por
  `app.isPackaged`. No inventar un mecanismo nuevo.
- **asar:** dejar el default (`true`).
- Versión: `0.2.0` (semver estricto — sufijos `a/b/c` rompen el parseo del updater; para
  arreglos posteriores incrementar el patch: 0.2.1, 0.2.2…).
- Recablear el `build` del `package.json` raíz, que todavía llama a `npm run tauri`.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Config de empaquetado de Tauri (spec autoritativo del comportamiento a replicar)
- `apps/desktop/src-tauri/tauri.conf.json` **en `a50659c^`** (borrado en `a50659c`, vivo en
  la historia de git) — NSIS (`languages: [Spanish, English]`, `displayLanguageSelector`,
  `licenseFile: EULA.txt`, `installerHooks`), `externalBin`, `resources` (extensión +
  `_internal`), endpoint del updater y pubkey minisign, `createUpdaterArtifacts`.
  Recuperar con: `git show a50659c^:apps/desktop/src-tauri/tauri.conf.json`
- `apps/desktop/src-tauri/installer-hooks.nsh` **en `a50659c^`** — el `NSIS_HOOK_PREINSTALL`
  con el `taskkill` del sidecar, y el comentario que explica POR QUÉ existe.

### Contratos de runtime que el empaquetado debe satisfacer
- `apps/desktop/electron/main/sidecar.ts` §`resolveSidecarExe` — fija el layout
  `resources/nyanko-api/nyanko-api.exe`. El empaquetado se adapta a esto, no al revés.
- `apps/backend/nyanko_api/main.py` §`extension_bundle` (~línea 2911) — fija que la extensión
  vive junto al exe del sidecar. Fuente de D-06.
- `apps/desktop/electron/main/index.ts` §`before-quit` / `killSidecar` — el updater debe
  reusar esta misma función antes de `quitAndInstall`.

### Estado y requisitos
- `.planning/phases/04-native-feature-parity/04-VERIFICATION.md` — frontmatter `deferred:`
  documenta el riesgo del icono no empaquetado que esta fase debe cerrar.
- `.planning/REQUIREMENTS.md` §PKG-01, §PKG-02, §DATA-01.

### Flujo de release existente
- Clave minisign: `$USERPROFILE\.tauri\nyanko-updater.key`, password vacía (Git Bash).
- Releases desde `main`; notas de release y commits en inglés.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `resolveSidecarExe()` (`electron/main/sidecar.ts:37`): ya implementa el patrón
  override-env → `process.resourcesPath`. El icono debe reusar esta forma, no inventar otra.
- `killSidecar()` (`electron/main/index.ts`): teardown ya escrito y probado, con comentario
  que anticipa explícitamente su uso desde el updater de esta fase.
- Scripts de build ya existentes en el `package.json` raíz: `build:sidecar` (PyInstaller),
  `build:icons`, `build:extension`. Reutilizables tal cual — solo hay que cambiar el paso
  final (`npm run tauri build` → `electron-builder`).

### Established Patterns
- PyInstaller onedir produce `apps/backend/dist/nyanko-api/{nyanko-api.exe, _internal/}` —
  la forma exacta que `extraResources` necesita copiar como una unidad.
- `app.isPackaged` es el discriminador dev/prod en todo el main (`isDevMode()`), con
  overrides por env var para poder testear el camino de prod.

### Integration Points
- `electron-updater` engancha en el main; debe llamar `killSidecar()` antes de
  `quitAndInstall(true)`.
- El `.nsh` custom (taskkill + posible uninstall de Tauri) se engancha vía
  `nsis.include` de electron-builder.
- El `build` del `package.json` raíz todavía invoca Tauri — hay que recablearlo.

</code_context>

<specifics>
## Specific Ideas

- El puente de D-01 es de un solo uso: una vez que la base instalada está en Electron, el
  `latest.json` y la clave minisign dejan de tener función. No hay que mantenerlos vivos.
- La verificación de D-02 (¿el uninstall silencioso borra `%APPDATA%`?) tiene que hacerse
  contra una instalación Tauri real, no razonando sobre el código del uninstaller.

</specifics>

<deferred>
## Deferred Ideas

- **CI en GitHub Actions** para buildear y publicar al taggear — más robusto que el build
  local, pero el sidecar necesita Python + PyInstaller en el runner: es una fase en sí misma,
  no parte del engine-swap. Backlog.
- **Firma de código con certificado real** + página "Verify" (minisign/cosign) — ya está en
  v2/Deferred de REQUIREMENTS.md. El instalador de esta fase debe quedar *firmable a futuro*,
  no firmado.

</deferred>

---

*Phase: 5-packaging-auto-update*
*Context gathered: 2026-07-11*
