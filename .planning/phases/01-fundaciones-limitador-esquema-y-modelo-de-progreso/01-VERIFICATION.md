---
phase: 01-fundaciones-limitador-esquema-y-modelo-de-progreso
verified: 2026-07-13T15:10:00Z
status: passed
score: 5/5 must-haves verified
plans_covered: [01-01, 01-02, 01-03, 01-04]
requirements: [FND-01, FND-02, FND-03, FND-04, FND-05, FND-06]
behavior_unverified: 0
overrides_applied: 0
re_verification:
  previous_status: passed
  previous_score: 5/5
  previous_warnings: [W-1, W-2, W-3]
  gaps_closed:
    - "W-1 — la lista blanca de FND-05 eximía por COLUMNA mientras el bug es del VALOR. Cerrada por 01-04 con una segunda capa NO EXENTABLE (find_loopback_urls). Dientes verificados por mutación."
    - "W-2 — next_progress declaraba tracker_status y nunca lo leía. Parámetro eliminado (dbc194e); is_reread lo conserva y sí lo lee. Spec corregida."
    - "W-3 — FND-05 marcado [x] en REQUIREMENTS.md (línea 87 y tabla, línea 277). Verificado que el check está GANADO, no puesto a mano."
  gaps_remaining: []
  regressions: []
notes:
  - id: N-1
    severity: info
    title: "La BD de producción REAL tiene 4.719 filas envenenadas AHORA MISMO — pero se auto-curan"
    detail: >
      Corriendo la nueva find_loopback_urls contra la BD de producción CRUDA (no la copia migrada):
      media_details_cache.cover_image_local = 2.784 filas y banner_image_local = 1.935 filas, todas
      con la forma 'http://127.0.0.1:8765/assets/...'. Muestreé los valores: NO son falsos positivos,
      es el bug original, vivo en disco. Se curan solas: _migrate_asset_urls_to_relative
      (database.py:404) corre INCONDICIONAL e idempotente en cada initialize(), y por eso la copia
      migrada a v8 sale limpia. No es una regresión de 01-04: la guardia de prefijo de 01-03 también
      las habría marcado (cover_image_local empieza por http y NO está exenta) — es exactamente el
      motivo por el que el plan 01-03 mandaba correr el script contra la copia migrada, no contra la
      v7 cruda.
    consequence: >
      `python scripts/check_persisted_urls.py` SIN argumento apunta por defecto a la BD de producción
      cruda y sale 1 con esas 4.719 filas. Es un verdadero positivo sobre datos sin curar, pero a
      quien lo corra a pelo le parecerá un fallo. Pásale siempre la copia migrada que imprime
      verify_real_db_migration.py, como dice su propio docstring.
  - id: N-2
    severity: info
    title: "El techo del chequeo loopback: hosts loopback, no cualquier host:puerto"
    detail: >
      _LOOPBACK_HOSTS = ('127.0.0.1', 'localhost', '[::1]'). Una URL a la LAN
      ('http://192.168.1.5:8765/assets/...') o a 0.0.0.0 NO se caza. Hoy es correcto — el sidecar
      liga a 127.0.0.1 — y ampliarlo a «cualquier host con puerto» arriesga falsos positivos sobre
      CDNs remotos legítimos, que es justo lo que apagaría la guardia. Techo deliberado y bien elegido.
  - id: N-3
    severity: info
    title: "La guardia DETECTA, no PREVIENE, en el camino de escritura"
    detail: >
      add_wont_watch (main.py:3992) sigue guardando body.cover_image verbatim: un cliente que POSTee
      una URL loopback la persiste, y la guardia solo la caza después (en tests, o al correr el
      script contra datos reales). FND-05 pide literalmente «con test de guardia que falla si...» —
      define el mecanismo como un test, y ese test existe y tiene dientes. El check está ganado. Se
      anota el residuo para que nadie crea que el camino de escritura está cerrado con llave.
---

# Phase 1: Fundaciones — limitador, esquema y modelo de progreso — Verification Report

**Phase Goal:** Nada en el milestone hace una ráfaga ni escribe una fila hasta que el limitador limita de verdad y el modelo de progreso está escrito, decidido y migrado contra una copia de la BD real.
**Verified:** 2026-07-13 (re-verificación tras el cierre de lagunas 01-04)
**Status:** ✅ **passed — 5/5 criterios, 6/6 requisitos FND. Sin lagunas pendientes.**
**Plans covered:** 01-01, 01-02, 01-03, 01-04

## Veredicto

**La Fase 01 está completa.** Los seis requisitos FND se cumplen con evidencia en el código, y las dos
lagunas que levantó la verificación anterior están cerradas de verdad — no declaradas cerradas: las
verifiqué por mutación y contra la BD real.

## Método

Ninguna afirmación de los SUMMARY se dio por buena. Los tres bugs del limitador y la nueva capa
loopback se sometieron a **mutación**: se rompió el arreglo a propósito y se comprobó que los tests se
ponen ROJOS. El chequeo de falsos positivos se ejecutó **contra la BD real**, no contra el fixture.
Todos los ficheros quedaron restaurados byte a byte (`git status` limpio).

## Goal Achievement

| # | Success Criterion | Status | Evidence |
|---|-------------------|--------|----------|
| 1 | Ráfaga de 50 desde los DOS event loops sin `RuntimeError` ni cuelgue; ritmo del header | ✓ VERIFIED | Mutación C (estado compartido) → `test_burst_from_two_event_loops` + poda en ROJO |
| 2 | Tras 429 se degrada y se recupera; ningún test pasa por hardcodear 90/30 | ✓ VERIFIED | `_observe_budget` en `http.py:207`, ANTES de `raise_for_status` (208). Pacing sobre `[120, 45, 12]`. Mutación A → 10 ROJOS |
| 3 | Migración v8 contra copia de la BD real: integridad, recuentos, backup | ✓ VERIFIED | Ejecutado: `integrity_check: ok -> ok`, 7→8, recuentos idénticos en 25 tablas, backup, original intacta |
| 4 | 10.5 REAL en local, floor() al proveedor, guarda contra el TRACKER, `progress_before` en cada sync | ✓ VERIFIED | Columna REAL migrada. `progress_before` en todos los caminos confirmados; `test_progress.py` afirma el valor **del tracker** (7), no el local (3). `undo_playback` falla cerrado |
| 5 | Un test de guardia falla si CUALQUIER columna persistida empieza por `http` | ✓ VERIFIED + **REFORZADO por 01-04** | Guardia genérica por `PRAGMA table_info` + **segunda capa NO EXENTABLE**. Dientes por mutación. 0 falsos positivos contra la BD real |

**Score:** 5/5 · **Requisitos:** FND-01 ✓ FND-02 ✓ FND-03 ✓ FND-04 ✓ FND-05 ✓ FND-06 ✓

## El delta de 01-04, auditado

### 1. El ensanchamiento a substring — **SÓLIDO. No es scope creep: cierra un agujero que el prefijo no puede ver**

Era la preocupación principal, y la respuesta es que el ejecutor tiene razón.

**El argumento del JSON es correcto, y lo comprobé.** `cache.payload` empieza por `{`, así que
`LIKE 'http%'` **es estructuralmente ciego** a una portada envenenada embutida dentro del JSON — y esa
portada la sirve el backend igual, y muere con el puerto igual. Un chequeo de *prefijo* no puede cubrir
esa clase de veneno, por mucho que se afine. La única forma de verlo es mirar dentro del valor. El
ensanchamiento no es «más de lo pedido»: es lo mínimo que cierra el hueco.

**Verifiqué yo mismo la afirmación de cero falsos positivos** (no la acepté de palabra), contra la copia
v8 real de 31,9 MB — el objetivo canónico que el plan 01-03 fijó:

```
214 columnas inspeccionadas · 421.688 valores no nulos barridos
find_loopback_urls -> ZERO hits
12.610 filas de URL remota legítima (CDN de AniList, nyaa.si) -> ninguna marcada
exit 0
```

**Cero falsos positivos, confirmado de forma independiente.** Lo que hace segura la ampliación es el `//`
delante del host (`%//127.0.0.1%`, no `%127.0.0.1%`): la palabra «localhost» suelta en una sinopsis no
puede acertar. El fallo que temía el SUMMARY de 01-03 —«una guardia que le grita a datos legítimos es una
guardia que alguien apaga»— **no se materializa**: la guardia no le grita a nada legítimo.

Techo, correctamente elegido (N-2): caza hosts *loopback*, no «cualquier host con puerto». Una URL a la
LAN no se caza. Ampliarlo más sí arriesgaría falsos positivos sobre CDNs remotos — que es exactamente lo
que apagaría la guardia. El techo está donde debe.

### 2. Los dientes — **CONFIRMADOS por mutación**

Neutralicé `find_loopback_urls` (vuelta al comportamiento de 01-03):

```
FAILED test_loopback_url_fails_even_in_an_allowlisted_column[http://127.0.0.1:8765/...]
FAILED test_loopback_url_fails_even_in_an_allowlisted_column[http://localhost:8765/...]
FAILED test_loopback_url_fails_even_in_an_allowlisted_column[http://[::1]:8765/...]
FAILED test_loopback_url_fails_even_in_an_allowlisted_column[https://127.0.0.1:8765/...]
FAILED test_loopback_url_hidden_inside_a_json_payload_is_caught
5 failed, 7 passed
```

La guardia **puede fallar**, y falla exactamente donde debe. El RED-before-GREEN que reclama el SUMMARY
es real.

### 3. `test_allowlist_never_covers_local_columns` — **INTACTO, byte por byte**

`git diff 43c45ab..HEAD` no toca ni una línea de la regla dura (`endswith("_local")` / `endswith("path")`).
No se debilitó nada para que pasaran los tests nuevos.

Detalle que además la refuerza: el test de dientes nuevo **afirma** que `("wont_watch","cover_image")`
sigue en la lista blanca — si alguien «arreglara» el problema quitando la exención, el test se rompería.
Eso mantiene la exención honesta en vez de taparla.

### 4. El `[x]` de FND-05 — **GANADO**

Cláusula uno («nada que contenga host o puerto se persiste jamás»), enforced por cuatro piezas reales:

- `_asset_url` (main.py:317) devuelve rutas **relativas** — el origen del bug, cerrado.
- `_migrate_asset_urls_to_relative` (database.py:404) **cura** lo ya escrito, incondicional e idempotente.
- La capa loopback **no exentable**: ninguna columna, exenta o no, puede apuntar al sidecar.
- El script contra datos reales, que mira **dentro** del valor.

Residuo honesto (N-3): la guardia **detecta**, no **previene** — `add_wont_watch` sigue guardando lo que
el cliente le manda. Pero FND-05 define su propio mecanismo como «con test de guardia que falla si…», y
ese test existe, tiene dientes y no es exentable. El check está ganado.

### 5. `tracker_status` (W-2) — **cerrado limpiamente**

Parámetro eliminado de `next_progress`. `is_reread` lo conserva **y sí lo lee** (`progress.py:57`), que
era el punto. `docs/specs/progress-model.md:68` corregida. `progress.py` sigue puro (único import: `math`).

## Hallazgo del verificador (N-1) — no es un defecto de la fase, pero hay que saberlo

Corriendo la nueva guardia contra la BD de producción **cruda** encontré **4.719 filas envenenadas
ahora mismo**:

```
media_details_cache.cover_image_local : 2.784 filas
media_details_cache.banner_image_local: 1.935 filas
  → 'http://127.0.0.1:8765/assets/anilist/21/cover.jpg'   (valores muestreados: reales)
```

Es el bug original, vivo en disco. **No es un falso positivo y no es una regresión de 01-04** — la
guardia de prefijo de 01-03 también las marcaba (`cover_image_local` empieza por `http` y no está
exenta). **Se curan solas** en el siguiente arranque de la app, porque
`_migrate_asset_urls_to_relative` corre incondicional en cada `initialize()`; por eso la copia migrada
a v8 sale limpia y el script sale 0 contra ella.

Consecuencia práctica: `check_persisted_urls.py` **sin argumento** apunta a la BD cruda y sale 1. Es un
verdadero positivo, pero parece un fallo. Pásale siempre la copia migrada, como dice su docstring.

## Behavioral Spot-Checks (ejecutados por el verificador)

| Check | Command | Result |
|-------|---------|--------|
| Suites de la fase | `pytest test_persisted_urls test_progress test_http -q` | **50 passed** in 4.05s (eran 44 → +6 de 01-04) |
| Migración v8 vs BD real | `python scripts/verify_real_db_migration.py` | integridad ok, 7→8, recuentos idénticos, backup, original intacta |
| Guardia (2 capas) vs copia v8 | `python scripts/check_persisted_urls.py <copia-v8>` | **exit 0**, 12.610 filas remotas legítimas, 0 violaciones, 0 loopback |
| Falsos positivos del substring | `find_loopback_urls` vs BD real migrada | **0 hits / 421.688 valores** |
| Dientes de la capa loopback | mutación: `find_loopback_urls -> []` | **5 failed** ✓ |

## Anti-Patterns

Ninguno. Sin `TODO`/`FIXME`/`XXX`/`TBD`/`HACK` en los ficheros de la fase. Los `ponytail:` presentes
nombran su techo (concurrencia 8, clamp del presupuesto, hosts loopback) — deuda declarada, no oculta.

## Gaps Summary

**Ninguna. La fase cierra.**

El limitador limita de verdad y sus tres bugs no pueden volver en silencio (probado por mutación). El
esquema v8 está migrado contra los 31,9 MB reales con integridad, recuentos y backup. El modelo de
progreso está escrito, es puro y está testeado, sin parámetros que mientan. Y la guardia de URLs tiene
ahora dos capas, la crítica de las cuales **no se puede eximir** — cerrando el agujero por el que el bug
que se llevó las portadas podía volver a entrar.

Las tres notas (N-1, N-2, N-3) son informativas: ninguna bloquea, ninguna requiere plan de cierre.

---

_Verified: 2026-07-13 — goal-backward, con mutation testing y ejecución contra la BD real de producción_
_Verifier: Claude (gsd-verifier)_
