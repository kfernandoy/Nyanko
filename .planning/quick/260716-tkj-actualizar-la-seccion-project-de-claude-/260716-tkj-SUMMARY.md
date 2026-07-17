---
phase: quick-260716-tkj
plan: 01
subsystem: docs
tags: [claude-md, project-context, v0.3, milestone-alignment]
status: complete
requires: [.planning/PROJECT.md]
provides: [DOC-CLAUDEMD-V03]
affects: [.claude/CLAUDE.md]
tech-stack:
  added: []
  patterns: ["El bloque GSD:project-start se COPIA de PROJECT.md, no se redacta"]
key-files:
  created: []
  modified: [.claude/CLAUDE.md]
decisions:
  - "Edicion a mano del bloque Project en vez de `gsd-tools generate-claude-md`: el comando regenera los siete bloques y re-apunta Stack a research/STACK.md (363 lineas), llevando CLAUDE.md de 84 a 284 lineas inyectadas en cada sesion"
  - "Ejecutado in-place en main, sin worktree: el worktree salia de origin/main (117 commits atras) y su PROJECT.md era el de 0.2 — copiar de ahi habria escrito el texto INVERSO al pretendido"
metrics:
  duration: ~6min
  completed: 2026-07-16
---

# Quick Task 260716-tkj: Actualizar la seccion Project de CLAUDE.md Summary

El bloque `GSD:project-start` de `.claude/CLAUDE.md` — inyectado en cada sesion de este repo —
dejo de afirmar que el shell es Tauri 2 y que construir features viola el scope; ahora dice Electron
y lleva el core value de 0.3 (el manga se lee dentro de la app), copiado literal de PROJECT.md.

## Que se entrego

Una sustitucion de bloque en un solo fichero. Los otros seis bloques marcados quedan byte-identicos.

| Antes (0.2, falso) | Ahora (0.3, copiado de PROJECT.md) |
|---|---|
| «Hoy el shell de escritorio es Tauri 2 (frontend React/Vite + Rust)» | «El shell de escritorio es Electron (electron-vite: main + preload + renderer React/Vite)» |
| Core value: «el tracking funciona identico tras cambiar el motor» | Core value: «el manga se lee dentro de la app, y el tracking ocurre solo» |
| Bullet **Scope**: «0.2 es engine-swap puro — nada de features nuevas» | Bullet **Versionado**: semver estricto, 0.2.x fixes / 0.3.0+ features |
| «sidecar PyInstaller onedir **sin cambios**» | «sidecar Python PyInstaller onedir» |
| «`webSecurity:true` **desde el dia 1**» | «`webSecurity:true`» |
| «Windows es el target primario **(igual que hoy)**» | «Windows es el target primario» |

El dano real era el bullet **Scope**: con el milestone activo siendo v0.3 «Nyanko lee manga», le decia
a cada agente que construir el reader violaba el scope. Ya habia obligado a un revisor a razonar a la
contra durante la planificacion de la Fase 4.

## Verificacion — REAL, ejecutada

**El gate del plan imprime `VERDE`, exit 0.** Se observo ROJO antes y VERDE despues; no es una
suposicion.

Estado ANTES (medido, no razonado):

```
--- stale literals present? ---
10:gratuita orientada a comunidad. Hoy el shell de escritorio es Tauri 2 (frontend
22:- **Scope**: 0.2 es engine-swap puro — nada de features nuevas (regla dura por
26:  TypeScript; sidecar Python PyInstaller onedir sin cambios.
29:  `webSecurity:true` desde el día 1.
31:- **Platform**: Windows es el target primario (igual que hoy).
--- new claims present? ---
0     <- El shell de escritorio es Electron
0     <- **Versionado**
0     <- el manga se lee dentro de la app
```

Los seis literales caducados presentes (la linea 10 lleva DOS: `Hoy el shell` y `Tauri 2`, por eso
son 5 hits de grep y no 6), las tres afirmaciones nuevas ausentes. Gate ROJO, como decia el encargo.

Estado DESPUES: `VERDE` / `GATE_EXIT=0`. Las siete comprobaciones encadenadas pasan:

1. Marcador de apertura sigue siendo la linea 1 ✓
2. Cada marcador aparece exactamente una vez ✓
3. Cero rastros de los seis literales de 0.2 en TODO el fichero ✓
4. Las tres afirmaciones nuevas presentes ✓
5. **La cola del fichero desde `GSD:stack-start` hasta el final es byte-identica a HEAD** (`diff` vacio) ✓
   — este es el gate real sobre «no toques nada mas»

| Comprobacion del plan | Resultado |
|---|---|
| Gate `<automated>` | **VERDE** (exit 0) |
| `git diff --stat` = UN fichero | ✓ `.claude/CLAUDE.md | 25 +++++------`, 1 file changed |
| `wc -l` cerca de 84, no ~284 | ✓ **87** (84 +3 netas) — prueba negativa de que `generate-claude-md` NO se ejecuto |
| `PROJECT.md` / `STACK.md` / `research/STACK.md` sin tocar | ✓ `git status --short` vacio para los tres |
| Borrados accidentales | ✓ ninguno (`git diff --diff-filter=D` vacio) |
| Ficheros sin trackear | ✓ ninguno |

## Desviaciones del plan

Ninguna. El plan se ejecuto exactamente como estaba escrito: una Tarea, un Edit, un commit.

Nota de ejecucion (decidida antes de spawnearme, no una desviacion mia): esta tarea corrio **in-place
en `main` sin aislamiento de worktree**. Un despacho previo con `isolation="worktree"` HALTO
correctamente con exit 42 — el worktree se creo desde `origin/main`, 117 commits por detras del `main`
local, asi que su `.planning/PROJECT.md` era el de la era 0.2. Copiar de ahi habria escrito
«engine-swap Tauri → Electron» en CLAUDE.md: el inverso exacto del proposito de la tarea. Verifique la
premisa antes de copiar nada — `PROJECT.md` linea 8 dice **Electron**, lineas 22-23 dan el core value
de manga. Arbol correcto, premisa intacta.

## Decisiones

**`gsd-tools generate-claude-md` NO se ejecuto** — prohibicion dura del encargo, verificada por el
recuento de lineas (87, no ~284). Es la via «oficial» y arregla el bloque Project bien, pero regenera
los siete bloques y re-apunta Stack a `.planning/research/STACK.md` (363 lineas de research),
triplicando lo que se inyecta en cada sesion para siempre. Medido, no supuesto: el comando **ignora
`--dry-run` y escribe de verdad** (esa escritura se hizo y se revirtio durante la planificacion). El
usuario vio el tradeoff y eligio la edicion a mano. Decision cerrada.

**Sin comentario de aviso dentro del bloque.** Un futuro `generate-claude-md` pisaria esta edicion.
El usuario lo sabe y lo acepta: nada corre ese comando automaticamente. Se declino explicitamente
anadir maquinaria o prosa defensiva contra eso.

## Notas para la siguiente sesion

- **El desfase de 117 commits entre `main` local y `origin/main` sigue abierto.** No se toco `origin`,
  no se hizo push: es una decision aparte que el usuario aun no ha tomado. Cualquier worktree creado
  desde `origin/main` seguira viendo el arbol de 0.2 y seguira siendo una trampa para tareas que lean
  `.planning/`.
- El fichero fuente (`PROJECT.md`) y el derivado (`CLAUDE.md`) vuelven a estar en fase. Si PROJECT.md
  cambia en el proximo milestone, este bloque hay que re-copiarlo a mano.

## Self-Check: PASSED

- `.claude/CLAUDE.md` — FOUND (87 lineas, bloque sustituido)
- `.planning/quick/260716-tkj-.../260716-tkj-SUMMARY.md` — FOUND (este fichero)
- Commit `17d6e4c` — FOUND en `git log`, 1 file changed, 14 insertions(+), 11 deletions(-)
- Gate del plan — ejecutado, imprime `VERDE`, exit 0
