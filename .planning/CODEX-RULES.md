# Contrato de ejecución para Codex (GSD)

Reglas de obligado cumplimiento cuando Codex ejecuta un plan GSD en este repo.
**Obedécelas a rajatabla. No las interpretes, no las optimices, no las saltes.**
Si una regla te impide terminar, PARA y dilo — no busques un rodeo.

---

## 1. Anclaje del repositorio

El repo es `E:/2023-09-04/anitracker/Nyanko`. La carpeta padre `anitracker` **NO es un repo git**.
Primera acción siempre: `git rev-parse --show-toplevel` para confirmar dónde estás. Nunca salgas de ahí.

## 2. PROHIBIDO ejecutar tests. Sin excepciones.

**No ejecutes `pytest` ni ningún test runner.** Nunca. Ni para "comprobar", ni para "verificar", ni "solo esta vez".

Motivo (esto no es una opinión, está medido): tu sandbox es `workspace-write` y tiene **denegado el TEMP del sistema**.
El fixture `tmp_path` de pytest no puede crear su directorio base, así que la suite te falla **aunque tu código sea correcto**.
Medición real: dentro de tu sandbox, `6 failed, 11 passed`; fuera, los mismos 17 tests dan `17 passed`.
Los 6 fallos son artefactos de tu jaula, no bugs.

**El orquestador ejecuta la suite fuera del sandbox y te dice el resultado real.** Ese es el gate.
Un `pytest` rojo en tu terminal **no significa nada** y no es motivo para tocar nada.

## 3. PROHIBIDO tocar la infraestructura de tests

No modifiques `conftest.py`, `pyproject.toml`, `pytest.ini`, ni el mecanismo de directorios temporales de ningún test.
**No inventes rutas de trabajo alternativas** (`.test-work`, `.pytest-tmp`, carpetas deterministas dentro del repo...).

Para directorios temporales en tests usa **siempre** el fixture `tmp_path` de pytest o `tempfile.TemporaryDirectory()`.
Es la stdlib y es lo correcto; que a ti te falle es problema de tu sandbox, no del test.

> Esto ya pasó una vez: al no poder correr pytest, se reescribió `_workdir()` para usar `Path(".test-work")`.
> Pasaba los tests y ensuciaba el repo con un directorio relativo dependiente del cwd. Hubo que revertirlo.
> **No repitas esto.**

## 4. NO intentes commitear. No puedes.

**No ejecutes `git add`, `git commit`, ni ningún comando que escriba en `.git/`.** Fallará siempre.

Motivo (medido, no teórico): tu sandbox `workspace-write` **deniega la escritura en `.git/`**.
`git add` muere con `fatal: Unable to create '.../.git/index.lock': Permission denied`.
No es una carrera, no es un lock colgado, no se arregla reintentando.

**El orquestador hace los commits** después de verificar tu trabajo. Tú entregas el árbol de trabajo
en su estado final y **reportas exactamente qué has tocado** para que él pueda commitearlo bien.

Lo que SÍ debes hacer: dejar el trabajo agrupado y coherente, y en tu respuesta final decir qué ficheros
corresponden a qué tarea del plan, para que los commits atómicos salgan correctos.

> **NUNCA simules commits, ni uses `--no-verify`, ni inventes hashes.** (La última vez lo hiciste bien:
> reportaste el bloqueo con exactitud en vez de fingir. Sigue así.)

Convenciones que el orquestador aplicará: mensajes en INGLÉS, un commit atómico por tarea, prefijo `(NN-MM)`.
Código y comentarios en ESPAÑOL — **eso sí es cosa tuya**.

## 5. SUMMARY.md

Escribe `<dir-de-la-fase>/<NN-MM>-SUMMARY.md` (formato: mira otros `*-SUMMARY.md` del repo).
**No lo commitees** (ver regla 4) — déjalo en el árbol de trabajo; el orquestador lo commitea.

En el self-check y en cada `status:` de coverage, escribe `unknown` / "pendiente de verificación por el
orquestador". **No inventes un resultado de tests** — tú no puedes ejecutarlos (regla 2).
El orquestador corre la suite, rellena los resultados reales y cierra el `status:`.

Tampoco ejecutes `roadmap.update-plan-progress`: escribe en `.planning/`, y eso también lo cierra el orquestador.

## 6. Alcance

Toca **solo** los ficheros listados en `files_modified` del frontmatter del PLAN.md. Ni uno más.
Si crees que necesitas tocar otro fichero, PARA y dilo en tu respuesta final.

## 7. Honestidad

Un orquestador verifica tu trabajo con gates deterministas: existencia de ficheros, `git log`, y `pytest` ejecutado fuera de tu sandbox.
**No afirmes que algo pasa si no lo has comprobado.** No marques un `must_have` como cumplido "por diseño".
Si algo queda a medias o dudas, dilo explícitamente en el SUMMARY.md y en tu respuesta final.
Un reporte optimista se detecta siempre y cuesta más caro que la verdad.

## 8. Respuesta final

Termina siempre con:
- Ficheros creados/modificados
- Hashes de los commits
- Qué NO has podido hacer (si aplica)
