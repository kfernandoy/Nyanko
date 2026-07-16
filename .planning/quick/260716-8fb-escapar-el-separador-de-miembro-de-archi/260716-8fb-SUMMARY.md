---
phase: quick-260716-8fb
plan: 01
subsystem: backend/sources
tags: [local-archive, page-pipe, bugfix, CR-01]
status: complete
dependency_graph:
  requires: [03-01 contrato v2 page_bytes]
  provides: [frontera archivo/miembro derivada de los datos]
  affects: [/assets/pages/{page_id:path}, ReaderView]
tech_stack:
  added: []
  patterns: [frontera derivada de las constantes, regex precompilado a nivel de modulo]
key_files:
  created: []
  modified:
    - apps/backend/nyanko_api/sources/local_archive.py
    - apps/backend/tests/test_sources.py
decisions:
  - La frontera archivo/miembro se deriva de ARCHIVE_EXTENSIONS | UNSUPPORTED_ARCHIVE_EXTENSIONS, no se adivina por el primer `!`
  - re.IGNORECASE en vez de .lower(): casa `.CBZ!` sin transformar la cadena, asi que los indices caen sobre el id ORIGINAL
  - re.ASCII obligatorio: sin el, `İ` (U+0130) casa con la `i` de `.zip`
metrics:
  duration: ~12 min
  completed: 2026-07-16
  tests: 452 passed (447 baseline + 5 nuevos)
requirements: [CR-01]
---

# Quick 260716-8fb: Escapar el separador de miembro de archivo — Summary

El `!` de un nombre de serie dejaba de confundirse con la frontera archivo/miembro: la frontera
ahora se deriva de la extension de archivo (`(\.cbr|\.cbz|\.rar|\.zip)!`), no del primer `!` que
aparezca. `Yotsuba&!`, `Bakuman!` y `Oh My Goddess!` vuelven a leerse enteras.

## Qué se hizo

`page_bytes()` partia el id por el PRIMER `!` (`page_id.split(ARCHIVE_MEMBER_SEPARATOR, 1)`). Como
`!` es un caracter legal y corriente en un titulo de manga, cada pagina de esas series daba 404 —
una clase entera de bibliotecas ilegible, con el core value de la Fase 03 fallando en silencio.

`page_bytes()` es el UNICO sitio del repo que parsea el separador (los demas tratan el id como
opaco: `main.py:347` solo lo URL-encoda, `engine.py:109` delega). Un arreglo ahi cubre a todos los
llamantes: no hubo que tocar ni la ruta, ni el engine, ni la API de manga.

| Tarea | Entrega | Commit |
|-------|---------|--------|
| 1 | Test de regresion parametrizado (5 casos) — RED verificado | `ea84237` |
| 2 | `_ARCHIVE_MEMBER_BOUNDARY` + parseo por `search()` en `page_bytes()` — GREEN | `7c7dbb8` |

## RED → GREEN (verificado, no asumido)

El plan delegaba los gates al orquestador por CODEX-RULES regla 2 (el sandbox de Codex tumba
`tmp_path`). Los ejecuté yo, que no estoy en ese sandbox, así que van los números reales:

**RED** — `pytest tests/test_sources.py -k regres` contra `local_archive.py` SIN modificar:

```
5 failed, 31 deselected
FAILED ...[regresion-bang-en-la-serie]          - SourceNotFoundError: Archivo local no encontrado
FAILED ...[regresion-bang-en-el-capitulo]       - SourceNotFoundError: Archivo local no encontrado
FAILED ...[regresion-bang-en-la-pagina]         - SourceNotFoundError: Archivo local no encontrado
FAILED ...[regresion-bang-en-la-ruta-del-cbz]   - SourceNotFoundError: Archivo local no encontrado
FAILED ...[regresion-extension-en-mayusculas]   - SourceNotFoundError: Archivo local no encontrado
```

5/5 fallan con el mismo sintoma que reprodujo CR-01, en `local_archive.py:194`. El test se commiteó
en rojo (`ea84237`) ANTES del arreglo, así que el RED está en la historia, no solo en un log.

**GREEN** — tras la Tarea 2: `5 passed, 31 deselected`.

**Suite entera:** `452 passed, 1 warning in 121.71s` (447 de baseline + los 5 nuevos). Cero
regresiones.

## Los dos fallos del fix propuesto en CR-01, confirmados ejecutándolos

El plan traía dos hallazgos del planner que corrigen el codigo concreto de CR-01. Los verifiqué
sobre el parser ya integrado:

**1. `.lower()` puede ALARGAR la cadena y desplazar el corte.** Medido:
`len('0:İstanbul!/Cap 2.CBZ!1.jpg')` = 27, pero `len(...lower())` = 28 — `'İ'.lower()` (U+0130)
devuelve DOS caracteres. CR-01 cortaba el id ORIGINAL por un indice calculado sobre la cadena
transformada. El parser nuevo no transforma nada:

| | archive_id | member |
|---|---|---|
| CR-01 (`.lower()`) | `0:İstanbul!/Cap 2.CBZ!` (se lleva el `!`) | `.jpg` (se come el `1`) |
| este (IGNORECASE) | `0:İstanbul!/Cap 2.CBZ` | `1.jpg` |

**2. `re.ASCII` es obligatorio.** Verificado: `B.search('0:x.zİp!1.jpg')` → `False` con el flag.
Sin el, esa `İ` casaria con la `i` de `.zip`.

**3. Orden determinista:** el `for ... in frozenset()` con `break` de CR-01 era de orden arbitrario
(el hash de `str` esta aleatorizado por proceso). `search()` devuelve la coincidencia mas a la
IZQUIERDA y el patron se construye con `sorted()`: mismo resultado en cada ejecucion.

## Comportamiento verificado del parser nuevo

Patron compilado: `(\.cbr|\.cbz|\.rar|\.zip)!`

| id | resultado |
|---|---|
| `0:Oh My Goddess!/Cap 1/001.jpg` | sin frontera → imagen suelta (antes: 404) |
| `0:Mi Serie.zip/Cap 1/001.jpg` | sin frontera → imagen suelta (el `.zip` va seguido de `/`, no de `!`) |
| `0:Serie.zip/Cap 1.cbz!1.jpg` | `('0:Serie.zip/Cap 1.cbz', '1.jpg')` — parte por el `.cbz!`, como debe |
| `0:Cap 3.cbr!1.jpg` | `('0:Cap 3.cbr', '1.jpg')` → sigue dando 415 "CBZ" |
| `0:Cap1.cbz!../../../etc/passwd` | `('0:Cap1.cbz', '../../../etc/passwd')` → SourceError (traversal cerrado) |

## Verificación de las restricciones duras del plan

- **`.cbr`/`.rar` en el patron:** `test_los_errores_de_pagina_son_tipados_y_no_exponen_paths` verde
  sin tocarlo. Es el que exige 415 con "CBZ" para `0:Cap 3.cbr!1.jpg`; sin `.cbr!` en el patron el
  id no partiria y saldria 404.
- **Traversal (D-05) intacto:** `git diff` confirma cero cambios en `_resolve_id` — el
  resolve-then-`relative_to` sigue igual. `test_page_bytes_rechaza_ids_fuera_de_la_biblioteca` y
  `test_el_endpoint_rechaza_traversal_sin_filtrar_rutas` verdes sin tocarlos (10 passed en la
  corrida dirigida).
- **`pages()` y `_make_id` sin tocar:** el productor siempre fue correcto; el bug estaba en el
  parseo. Confirmado por `git diff`.
- **Reader / RD-09 sin tocar:** solo 2 ficheros modificados, ambos backend.
- **Infra de tests intacta:** ni `conftest.py`, ni `pyproject.toml`, ni `pytest.ini`.
- **Cero dependencias nuevas:** `re` ya estaba importado.

## Deviations from Plan

Ninguna en el código — las dos tareas salieron como estaban escritas.

Una desviación de proceso, deliberada: el plan asignaba los gates (RED y suite) al orquestador por
CODEX-RULES regla 2, que aplica al sandbox de Codex. Este plan lo ejecutó Claude, sin esa jaula, así
que corrí los gates yo mismo y el SUMMARY va con `status: complete` y números medidos en vez del
`status: unknown` que pedía `<output>`. La regla existe porque Codex no PUEDE medir; no aplica a un
ejecutor que sí puede.

## Known Stubs

Ninguno.

## Threat Flags

Ninguna superficie nueva. El cambio solo mueve DONDE se corta el id; `_resolve_id` (T-8fb-01) y la
validacion del `member` contra `archive.namelist()` (T-8fb-02) siguen intactos. El patron
(T-8fb-03) son alternativas literales sin cuantificadores anidados: sin backtracking catastrofico,
y se compila una vez a nivel de modulo.

## Self-Check: PASSED

- `apps/backend/nyanko_api/sources/local_archive.py` — FOUND (modificado)
- `apps/backend/tests/test_sources.py` — FOUND (modificado)
- Commit `ea84237` (test RED) — FOUND en `git log`
- Commit `7c7dbb8` (fix GREEN) — FOUND en `git log`
- Suite: `452 passed` — EJECUTADA, no asumida
