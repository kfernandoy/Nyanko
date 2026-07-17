---
status: diagnosed
phase: 04-identidad-y-v-nculo-fuente-entrada-del-tracker
source: [04-VERIFICATION.md]
started: 2026-07-17T15:14:42Z
updated: 2026-07-17T16:05:00Z
---

## Current Test

[testing complete]

## Tests

### 1. Pulsar el boton de vincular de una serie sin vinculo (MangaLibraryView)
expected: Se abre el panel con la propuesta, un porcentaje de confianza visible y hasta 5 alternativas; la vista NO navega dentro de la carpeta.
result: issue
reported: "no veo ningun vinculo en la libreria de manga"
severity: major

### 2. Con teclado (Tab), la fila de una serie ofrece dos paradas de foco (navegar / vincular) y Enter en cada una hace lo suyo
expected: Dos controles de foco independientes, cada uno activable con Enter.
result: issue
reported: "no aparece nigun boton"
severity: major

### 3. Cerrar el panel de vinculo SIN pulsar confirmar, y reabrirlo
expected: La serie sigue sin vincular (mirar una propuesta no la acepta).
result: skipped
reason: "Bloqueado por el mismo problema de los tests 1-2: no hay boton de vincular con el que abrir el panel."

### 4. Elegir una alternativa distinta de la propuesta, fijar offset y confirmar
expected: El panel se cierra y la serie muestra la entrada ELEGIDA, no la propuesta original.
result: skipped
reason: "Bloqueado por el mismo problema de los tests 1-2: no hay boton de vincular con el que abrir el panel."

### 5. Reabrir el panel de una serie ya vinculada
expected: Sigue vinculada a lo elegido, y no se propone nada nuevo (el vinculo cortocircuita el matcher).
result: skipped
reason: "Bloqueado por el mismo problema de los tests 1-2: no hay boton de vincular con el que abrir el panel."

### 6. Desvincular una serie
expected: La serie vuelve a "sin vincular".
result: skipped
reason: "Bloqueado por el mismo problema de los tests 1-2: no hay boton de vincular con el que abrir el panel."

### 7. Reiniciar la app despues de confirmar un vinculo
expected: El vinculo persiste (esta almacenado, no en memoria).
result: skipped
reason: "Bloqueado por el mismo problema de los tests 1-2: no hay boton de vincular con el que abrir el panel."

### 8. Con DOS series distintas en la MISMA carpeta raiz (biblioteca plana), vincular solo la primera
expected: La segunda serie sigue viendose "sin vincular" (la clave es source_id, no series_id).
result: skipped
reason: "Bloqueado por el mismo problema de los tests 1-2: no hay boton de vincular con el que abrir el panel."

### 9. Terminar de leer un capitulo de una serie SIN vincular
expected: El lector muestra el mensaje "no vinculada, vinculala" en espanol (el reason del backend), no silencio.
result: skipped
reason: "Bloqueado por el mismo problema de los tests 1-2: no hay boton de vincular con el que abrir el panel."

### 10. Con una carpeta de biblioteca PLANA (CBZ colgando de la raiz, series_id/source_id = "0:.")
expected: Esa serie tambien se puede vincular y el vinculo sobrevive (no-regresion Fase 3).
result: skipped
reason: "Bloqueado por el mismo problema de los tests 1-2: no hay boton de vincular con el que abrir el panel."

## Summary

total: 10
passed: 0
issues: 2
pending: 0
skipped: 8
blocked: 0

## Gaps

- truth: "Se abre el panel con la propuesta, un porcentaje de confianza visible y hasta 5 alternativas; la vista NO navega dentro de la carpeta."
  status: failed
  reason: "User reported: no veo ningun vinculo en la libreria de manga"
  severity: major
  test: 1
  root_cause: "El boton de vincular se renderiza solo cuando `!capitulo.is_chapter` (MangaLibraryView.tsx:252). La unica carpeta de manga registrada del usuario (G:\\manga) es una biblioteca PLANA: los CBZ/CBR cuelgan directamente de la raiz, sin subcarpeta por serie. `local_archive.py:133` clasifica `is_chapter=not is_directory or has_images`, asi que en una raiz plana TODAS las filas salen `is_chapter=true` — cero filas de serie, cero botones de vincular, para cualquier usuario con esta estructura. No es un bug de logica (el condicional esta bien escrito para bibliotecas con subcarpeta por serie); es un caso que 04-04-PLAN.md nombro en su paso 10 de human-check pero nunca especifico que elemento de UI deberia llevar el vinculo cuando la 'serie' es la propia carpeta raiz."
  artifacts:
    - path: "apps/desktop/src/MangaLibraryView.tsx"
      issue: "El boton `manga-library-link` (linea ~252) solo se renderiza por fila cuando `!capitulo.is_chapter`; una biblioteca plana no tiene ninguna fila asi."
    - path: "apps/backend/nyanko_api/sources/local_archive.py"
      issue: "Linea 133: `is_chapter=not is_directory or has_images` clasifica todo archivo suelto en la raiz como capitulo, nunca como serie vinculable."
  missing:
    - "Decision de producto: como se vincula una carpeta raiz plana (sin subcarpeta de serie) — ver test 10, que pide exactamente este caso y hoy tambien falla por la misma causa."
    - "Un affordance de vinculo a nivel de carpeta/ruta (p.ej. keyed por `carpeta.id:.`) cuando el listado es plano, en vez de depender de una fila de serie que no existe."
  debug_session: .planning/debug/manga-link-button-missing.md
- truth: "Dos controles de foco independientes, cada uno activable con Enter."
  status: failed
  reason: "User reported: no aparece nigun boton"
  severity: major
  test: 2
  root_cause: "Mismo root cause que el gap del test 1 — cero filas de serie en esta biblioteca plana, asi que ningun boton de vincular existe para poder enfocarlo."
  artifacts:
    - path: "apps/desktop/src/MangaLibraryView.tsx"
      issue: "El boton `manga-library-link` no se renderiza para ninguna fila en una biblioteca plana."
  missing:
    - "Misma resolucion que el gap del test 1 — no es un segundo bug independiente."
  debug_session: .planning/debug/manga-link-button-missing.md
