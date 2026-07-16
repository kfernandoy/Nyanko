---
phase: quick-260716-amb
plan: 01
subsystem: biblioteca-local
tags: [schema-migration, library-folders, uat-fix]
requires: []
provides:
  - library_folders.kind (anime/manga/ambas), esquema v10
  - filtro por tipo en iter_video_files (anime) y LocalArchiveSource._load_roots (manga)
  - selector de tipo en Ajustes → Carpetas de la biblioteca (ES + EN)
affects:
  - apps/backend/nyanko_api/database.py
  - apps/backend/nyanko_api/scanner.py
  - apps/backend/nyanko_api/sources/local_archive.py
  - apps/desktop/src/LibrarySettingsView.tsx
tech-stack:
  added: []
  patterns:
    - "_add_column idempotente + default de columna = migración completa (precedente: torrent_sources.kind, database.py:380)"
    - "filtro en el consumidor único, no en la query ni en los llamantes"
key-files:
  created: []
  modified:
    - apps/backend/nyanko_api/database.py
    - apps/backend/nyanko_api/scanner.py
    - apps/backend/nyanko_api/sources/local_archive.py
    - apps/backend/nyanko_api/models.py
    - apps/backend/nyanko_api/main.py
    - apps/backend/tests/test_database.py
    - apps/backend/tests/test_scanner.py
    - apps/backend/tests/test_sources.py
    - apps/backend/tests/test_reader_persistence.py
    - apps/desktop/src/types.ts
    - apps/desktop/src/api.ts
    - apps/desktop/src/LibrarySettingsView.tsx
    - apps/desktop/src/i18n.tsx
decisions:
  - "Migración y default de columna coinciden en 'ambas' por razones distintas (preservación de datos / compatibilidad de escritores): que coincidan es lo que permite que un solo ALTER TABLE haga las dos cosas"
  - "El filtro vive en los 2 consumidores, no en get_library_folders ni en los 5 llamantes: un llamante nuevo hereda el filtro por construcción"
metrics:
  duration: ~25min
  completed: 2026-07-16
  tasks: 3
  files: 13
status: complete
---

# Quick 260716-amb: Carpetas de biblioteca con tipo (UAT #2) Summary

Columna `kind` (anime/manga/ambas) en `library_folders`, esquema v10, con el filtro en los **dos
consumidores** (`iter_video_files` y `_load_roots`) en vez de en la query o en los llamantes: añadir una
carpeta de manga ya no dispara el escaneo de anime, y las carpetas que ya existen migran a `ambas`, así
que su comportamiento de hoy no cambia.

## Qué se hizo

| Tarea | Commit | Qué |
|-------|--------|-----|
| 1 | `c051ee5` | Tests **en rojo** (precedente `ea84237`): migración v9→v10, filtro de scanner, filtro de sources, pines de compatibilidad |
| 2 | `0f9e24d` | `kind` en el esquema + v10 + filtro en los dos consumidores + los 7 pines de versión |
| 3 | `1faab19` | `<select>` de tipo al añadir y por fila; `toggleRecursive` pasa `folder.kind`; i18n ES+EN |

## El RED, observado y no asumido

Los 4 tests de comportamiento fallaron **cada uno por el motivo que el plan predijo**:

| Test | Fallo real |
|------|-----------|
| `test_v9_library_folders_migran_a_ambas` | `sqlite3.OperationalError: no such column: "kind"` — el `DROP COLUMN` del helper revienta |
| `test_new_database_has_library_folder_kind_defaulting_to_ambas` | `AssertionError: assert 'kind' in {'created_at', 'id', 'path', 'recursive'}` |
| `test_iter_video_files_skips_manga_folders` | `AssertionError: assert 3 == 2` — la carpeta de manga aparece |
| `test_local_archive_skips_anime_folders` | `AssertionError: ...nyanko-kind-roots.../anime not in {...}` — la de anime está en las raíces |

`4 failed, 96 passed` antes del arreglo. Tras la Tarea 2, los cuatro pasaron a verde **sin tocarlos**.

**Los 2 tests de compatibilidad (`kind` ausente) salieron VERDES en el RED, y es correcto**: son pines
del comportamiento de hoy, no tests de comportamiento nuevo — el plan los pide explícitamente como «el
caso que fija la compatibilidad». No son tautologías: muerden contra un arreglo ingenuo (un
`folder.get("kind") not in ("anime","ambas")` sin el `or "ambas"` los tumbaría con `0 == 1`). Se deja
dicho aquí porque la instrucción «un test nuevo que salga verde está mal escrito» aplicaba a los 4 de
comportamiento, no a los pines.

## Verificación

| Gate | Resultado |
|------|-----------|
| `cd apps/backend && .venv/Scripts/python.exe -m pytest -q` | **461 passed** (baseline 455 + 6 nuevos), ejecutado en HEAD final |
| `npm run check` (tsc) | verde |
| `grep -n "get_library_folders" apps/backend/nyanko_api/main.py` | los 7 sitios **sin parámetro de tipo**: el filtro está en los consumidores |
| `test_reader_persistence.py` / `test_persisted_urls.py` (guarda FND-05) | verdes, sin tocar `assert_no_persisted_urls` |

## Decisiones

**Un solo `ALTER TABLE` es la migración entera.** `_add_column(connection, "library_folders", "kind",
"TEXT NOT NULL DEFAULT 'ambas'")` — SQLite rellena las filas existentes con el default. Cero funciones
`_migrate_*` nuevas, cero `UPDATE` de backfill. Precedente idéntico ya en el fichero (`database.py:380`,
`torrent_sources.kind`). El `SCHEMA` y el `_add_column` llevan la MISMA definición de columna.

**Los dos defaults coinciden en `ambas`, por razones distintas.** Migración = preservación de datos (una
carpeta que hoy sirve para las dos cosas tiene que seguir sirviendo para las dos; lo contrario sería
pérdida de datos silenciosa, contra el Core Value). Default de columna = compatibilidad de escritores
(fallar a `ambas` = escanear de más, molesto e inofensivo; fallar a `anime`/`manga` = invisible en
silencio, que es el bug que se arregla).

**El filtro en los 2 consumidores.** `get_library_folders()` sigue devolviendo todas las carpetas: la
lista de Ajustes y el lookup por id las necesitan. Los 2 caminos de anime pasan todos por
`iter_video_files()`; los 3 de manga por `_load_roots()`. 2 guardas, 0 llamantes tocados, y el sexto
llamante que llegue mañana hereda el filtro. Es la lección de la Fase 01 que STATE.md ya tiene escrita:
«un invariante mantenido en cuatro sitios se rompe, uno derivado al leer no».

**La trampa del upsert, cerrada.** `add_library_folder` escribe ahora `kind = excluded.kind`, así que
`toggleRecursive` pasa `folder.kind` — sin eso, tocar «incluir subcarpetas» le habría reseteado el tipo
a la carpeta. Es un must-have del plan y está en el código con un comentario que dice por qué.

## Desviaciones del plan

Ninguna. El plan se ejecutó como estaba escrito.

Una nota de proceso: el plan asignaba la ejecución de pytest al orquestador por CODEX-RULES regla 2 (el
sandbox de Codex tumba `tmp_path`). Esta ejecución la hizo Claude, que sí puede correr la suite y
commitear, así que el RED y el verde son números reales medidos aquí, no delegados.

## Known Stubs

Ninguno.

## Self-Check: PASSED

- Ficheros modificados: los 13 existen y están commiteados.
- Commits: `c051ee5`, `0f9e24d`, `1faab19` presentes en `git log`.
- Suite: 461 passed, ejecutada en HEAD final (no inferida de una corrida anterior).
- tsc: verde.

## Pendiente

**UAT manual (usuario)**: añadir una carpeta de manga y confirmar que NO arranca el escaneo de anime.
Es el punto 5 de la verificación del plan y no se puede automatizar aquí.

Los hallazgos **#3 / #4 / #5** del UAT (ajuste «alto», scroll vertical, numeración de página) siguen
abiertos: van en sus propias tareas. El reader no se tocó.
