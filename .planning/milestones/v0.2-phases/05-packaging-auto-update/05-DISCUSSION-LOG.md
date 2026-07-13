# Phase 5: Packaging + auto-update — Discussion Log

**Date:** 2026-07-11
**Mode:** discuss (default)

Registro para auditoría humana. Los agentes downstream leen `05-CONTEXT.md`, no este archivo.

## Áreas presentadas

El usuario seleccionó las cuatro: puente 0.1.15 → Electron, modo del instalador NSIS,
recursos (sidecar/extensión/icono), publicación del release.

---

## Área 1 — Puente 0.1.15 → Electron

**Contexto aportado:** el updater de Tauri baja el NSIS, verifica minisign y lo ejecuta —
es agnóstico al framework que generó el instalador. La clave privada minisign existe
(`~/.tauri/nyanko-updater.key`), así que la auto-migración es técnicamente posible.

**Pregunta:** ¿cómo llegan a Electron los que hoy corren 0.1.15?

| Opción | Elegida |
|---|---|
| Auto-migración firmada (firmar el NSIS de Electron con la clave minisign vieja) | ✅ |
| Corte limpio (descarga manual, los de 0.1.15 quedan varados) | |
| Auto-migración sin desinstalar (acepta entrada duplicada) | |

→ **D-01**

### Seguimiento: riesgo de pérdida de datos

Se levantó que el desinstalador NSIS de Tauri ofrece borrar los datos de la aplicación, y
esos datos son `%APPDATA%\app.nyanko.desktop` — la biblioteca del usuario. Un
`uninstall.exe /S` a ciegas podría borrarle la biblioteca a toda la base instalada.

**Pregunta:** ¿cómo se quita la instalación vieja sin arriesgar la biblioteca?

| Opción | Elegida |
|---|---|
| Instalar encima, no desinstalar nunca | |
| Uninstall silencioso **+ verificación empírica previa** (fallback: instalar encima) | ✅ |
| Backup defensivo de la carpeta de datos + uninstall | |

→ **D-02** (con gate bloqueante: hay que probarlo en una instalación real antes de cablearlo)

---

## Área 2 — Modo del instalador NSIS

**Contexto aportado:** se deshizo un falso dilema — `quitAndInstall(isSilent = true)` da
updates silenciosos incluso con un instalador asistido, así que paridad y silencio no son
excluyentes. Lo que sí es decisión real es el alcance de instalación.

**Pregunta:** ¿per-user o per-machine, y con qué paridad?

| Opción | Elegida |
|---|---|
| Asistido per-user (selector ES/EN + EULA, sin UAC) | ✅ |
| oneClick per-user (más simple, pierde paridad y EULA) | |
| Asistido per-machine (UAC en cada update → rompe el update silencioso) | |

→ **D-03**, **D-04**

---

## Área 3 — Recursos

**Hallazgo durante el scouting:** el backend resuelve la carpeta de la extensión como
`Path(sys.executable).parent / "extension"` (`main.py:2924`). Copiar el layout de Tauri
(`resources/extension/`) habría dejado el botón "abrir carpeta de la extensión" devolviendo
`null` en producción, sin error visible.

**Pregunta:** ¿empaquetar según lo que el backend espera, o enseñarle una env var al backend?

| Opción | Elegida |
|---|---|
| Empaquetar según el contrato existente (`resources/nyanko-api/extension/…`) | ✅ |
| Env var `NYANKO_EXTENSION_DIR` (layout limpio, pero toca el sidecar) | |

→ **D-06**, **D-07**. Descartada la segunda por la restricción de milestone: 0.2 es
engine-swap puro, el sidecar Python no se toca.

**No preguntado (discreción de Claude):** el icono y `asar`. El icono reusa el patrón que
`resolveSidecarExe()` ya establece; `asar` queda en su default.

---

## Área 4 — Publicación

**Contexto aportado:** `electron-updater` necesita un `latest.yml` con SHA512 y tamaño
exactos. Escribirlo a mano rompe el update de todos en silencio si el hash no coincide.

**Pregunta:** ¿cómo se publica 0.2.0?

| Opción | Elegida |
|---|---|
| electron-builder `--publish` + script aparte para el puente minisign | ✅ |
| Todo manual por API REST (como el flujo Tauri actual) | |
| CI en GitHub Actions | |

→ **D-08**. CI descartada por scope (necesita Python + PyInstaller en el runner; es una fase
en sí misma) → movida a Deferred.

---

## Ideas diferidas

- CI en GitHub Actions para build + publish al taggear.
- Firma de código con certificado real + página "Verify" (ya estaba en v2/Deferred).
