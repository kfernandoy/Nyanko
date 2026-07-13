---
phase: 01-fundaciones-limitador-esquema-y-modelo-de-progreso
verified: 2026-07-13T14:05:00Z
status: passed
score: 5/5 must-haves verified
behavior_unverified: 0
overrides_applied: 0
warnings:
  - id: W-1
    severity: warning
    title: "La lista blanca de FND-05 exime por COLUMNA, pero el bug es una propiedad del VALOR"
    detail: >
      REMOTE_URL_ALLOWLIST exime 6 (tabla, columna). Dentro de una columna exenta, la guardia no
      distingue 'https://s4.anilist.co/...' (legítimo) de 'http://127.0.0.1:8765/assets/...' (el bug
      que se llevó las portadas). `wont_watch.cover_image` es la ÚNICA entrada exenta alimentada por
      el CLIENTE: normalizeAssetUrls (apps/desktop/src/api.ts:204) reescribe todo '/assets/...' a
      '${apiUrl}/assets/...' — es decir, fabrica exactamente la URL con puerto dentro — y
      addWontWatch (api.ts:446) reenvía ese valor tal cual a add_wont_watch (main.py:3992), que lo
      guarda verbatim. Hoy es seguro SOLO porque /api/search/media sirve portadas del CDN remoto y
      nunca '/assets/...'. Esa propiedad no está enforced en ninguna parte.
    recommendation: >
      ~3 líneas en find_persisted_urls: las columnas exentas siguen exentas de LIKE 'http%', pero NO
      de un chequeo de loopback/puerto (http://127.0.0.1, http://localhost, o '://host:puerto').
      Cierra el hueco para las 6 entradas, no solo wont_watch, y deja verdes las 12.610 filas de CDN
      legítimo. Momento natural: al planificar la Fase 3 (el reader empieza a persistir URLs de página).
  - id: W-2
    severity: warning
    title: "next_progress declara un parámetro que su cuerpo nunca lee"
    detail: >
      progress.py:21 — `next_progress(chapter, tracker_progress, tracker_status=None)`. El cuerpo
      (líneas 35-43) NO usa `tracker_status` en ningún momento. La firma promete una sensibilidad al
      estado que la implementación no tiene: un llamador de la Fase 5 que pase tracker_status="COMPLETED"
      esperando otro resultado se llevará una sorpresa silenciosa. Ruff no lo detecta (ARG002 desactivada).
    recommendation: "O se usa, o se quita de la firma. Decidirlo antes de que la Fase 5 tenga llamadores."
  - id: W-3
    severity: bookkeeping
    title: "REQUIREMENTS.md sigue marcando FND-05 como pendiente"
    detail: "FND-01..04 y FND-06 están [x]; FND-05 sigue [ ] pese a estar implementado y verificado."
    recommendation: "Marcar FND-05 como [x] en .planning/REQUIREMENTS.md."
deferred:
  - truth: "El capítulo 10.5 se envía floor()eado (10) al proveedor (cláusula de SC-4, extremo a extremo)"
    addressed_in: "Phase 5"
    evidence: >
      Hoy NINGÚN camino de producción envía un capítulo de manga a un proveedor — no existe el reader
      (Fase 3) ni el sync de progreso (Fase 5). El modelo (to_provider/next_progress/effective_chapter)
      está escrito, es puro y está testeado; la columna chapter_progress REAL está migrada. El objetivo
      de esta fase es exactamente ese: que el modelo esté «escrito, decidido y migrado» ANTES de que
      exista un consumidor. Phase 5 goal: «Última página → el progreso sube solo al proveedor».
  - truth: "next_progress / is_reread / effective_chapter tienen cero call sites de producción"
    addressed_in: "Phase 3 y Phase 5"
    evidence: >
      Por diseño: son el contrato contra el que la Fase 3 (reader) y la Fase 5 (sync) construyen. Único
      símbolo ya cableado: to_provider, usado por Database.set_chapter_progress (database.py:2614).
---

# Phase 1: Fundaciones — limitador, esquema y modelo de progreso — Verification Report

**Phase Goal:** Nada en el milestone hace una ráfaga ni escribe una fila hasta que el limitador limita de verdad y el modelo de progreso está escrito, decidido y migrado contra una copia de la BD real.
**Verified:** 2026-07-13
**Status:** passed (5/5) — con 2 warnings y 1 corrección de contabilidad
**Re-verification:** No — initial verification

## Método

No se dio por buena ninguna afirmación de los SUMMARY. Cada criterio se comprobó contra el código, y
los tres del limitador se sometieron a **mutación**: se rompió a propósito el arreglo y se comprobó
que los tests se ponen ROJOS. Un test que no falla contra el bug no prueba nada, y esa es justamente
la trampa que este plan existía para evitar. `http.py` quedó restaurado byte a byte (`git diff` vacío).

## Goal Achievement

### Observable Truths (Success Criteria del ROADMAP)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Ráfaga de 50 concurrentes desde los DOS event loops sin `RuntimeError` ni cuelgue; el ritmo sale del `X-RateLimit-Limit` del proveedor | ✓ VERIFIED | `test_burst_from_two_event_loops` (hilo + `asyncio.run()`, re-lanza la excepción del hilo, `join(timeout)`). **Mutación C** (estado compartido entre loops) → ROJO en `test_burst_from_two_event_loops` y `test_loop_state_prunes_closed_loops`. |
| 2 | Tras un 429 se adapta al presupuesto degradado y vuelve al normal cuando el proveedor lo anuncia; ningún test pasa por hardcodear 90 ni 30 | ✓ VERIFIED | `_observe_budget` se llama en `http.py:207` **ANTES** de `raise_for_status()` (208) — el 429 es la única respuesta que trae el presupuesto degradado. Pacing parametrizado sobre `[120, 45, 12]`: ninguno es 90 ni 30. **Mutación A** (ignorar la cabecera) → 10 tests ROJOS. |
| 3 | La migración a v8 corre contra copia de la BD real, `integrity_check: ok`, mismos recuentos, backup pre-migración | ✓ VERIFIED | **Ejecutado por el verificador**: `integrity_check: ok -> ok`, `schema_migrations: 7 -> 8`, recuentos idénticos en las 25 tablas, `library_entries.chapter_progress: REAL`, backup creado, «BD original intacta (tamaño y mtime): sí». |
| 4 | 10.5 se guarda REAL en local y floor()eado al proveedor; guarda monotónica contra el valor DEL TRACKER; `progress_before` en cada sync | ✓ VERIFIED | Columna REAL migrada (verificado en la BD real). `set_chapter_progress` escribe la pareja coherente vía `to_provider`. `progress_before` cableado en TODOS los caminos confirmados; `test_progress.py:195` (parametrizado sobre 3 endpoints) afirma que graba el valor **del tracker** (7), no el local (3), ni 0, ni `progress_after`. Envío end-to-end al proveedor → deferred a Fase 5 (ver frontmatter). |
| 5 | Un test de guardia falla si CUALQUIER columna persistida empieza por `http`, incluidas las nuevas de v8 | ✓ VERIFIED | Guardia genérica por `sqlite_master` + `PRAGMA table_info` (cero listas escritas a mano). `test_guard_covers_columns_it_never_names` añade una columna en runtime y la guardia la caza sin ser editada. **Ejecutado por el verificador contra la copia v8 real de 31,9 MB**: exit 0, 12.610 filas de URL remota inspeccionadas → no pasa en vacío. Ver W-1. |

**Score:** 5/5 truths verified (0 behavior-unverified)

### Prueba de dientes (mutation testing ejecutado por el verificador)

| Mutación | Bug reintroducido | Resultado esperado | Resultado real |
|----------|-------------------|--------------------|----------------|
| A | `_observe_budget` ignora la cabecera (presupuesto horneado) | pacing + degrade en ROJO | **10 failed, 10 passed** ✓ |
| B | `sleep(self._interval)` de vuelta DENTRO del semáforo (la forma original) | `test_concurrent_requests_get_distinct_deadlines` en ROJO | **4 failed** — cae el de deadlines distintos y los 3 de pacing ✓ |
| C | Un solo `_LoopState` compartido entre todos los loops | `test_burst_from_two_event_loops` en ROJO | **5 failed** — cae el burst (AssertionError del hilo) y la poda ✓ |

Los tres bugs de FND-01/02/03 están genuinamente cubiertos: ninguno puede volver en silencio.

### Requirements Coverage

| Requirement | Status | Evidence |
|-------------|--------|----------|
| FND-01 (presupuesto de la cabecera) | ✓ SATISFIED | `RATE_LIMIT_HEADER` + `_observe_budget` con clamp `[1, ceiling]`; `999999/0/-5/""/abc/30.5` no desactivan el limitador. |
| FND-02 (soltar antes de dormir) | ✓ SATISFIED | `http.py:197-200`: reserva bajo `state.lock`, sale, duerme; `async with state.semaphore` (202) es solo tope EN VUELO. Ningún `sleep` léxicamente dentro del semáforo. |
| FND-03 (estado por event loop) | ✓ SATISFIED | `_loop_state: dict[AbstractEventLoop, _LoopState]`, gemelo de `_clients`, con poda de loops cerrados. Ningún primitivo asyncio en `__init__`. |
| FND-04 (modelo de progreso) | ✓ SATISFIED | `progress.py` puro (único import: `math`), 4 funciones, `docs/specs/progress-model.md` (105 líneas). `progress_before` cableado y testeado. |
| FND-05 (nada con host/puerto persistido) | ✓ SATISFIED (ver W-1) | Guardia genérica + script contra la BD real. **Sigue marcado `[ ]` en REQUIREMENTS.md → W-3.** |
| FND-06 (migración contra BD real) | ✓ SATISFIED | `verify_real_db_migration.py` ejecutado por el verificador contra los 31,9 MB reales. |

## Las tres desviaciones, auditadas

### 1. `01-01` — snapshot `list(...)` + `pop(stale, None)` en vez de replicar `_client_for` tal cual → **SÓLIDA, y mejor que el plan**

El ejecutor tenía razón. El `_client_for` original (`git show 8f4efc4^`) hacía:

```python
for stale in [known for known in self._clients if known.is_closed()]:
    del self._clients[stale]
```

La comprensión itera **el dict** ejecutando bytecode Python en el predicado (`known.is_closed()`), así que
el GIL puede ceder entre elementos: si el hilo del `MutationWorker` inserta su loop en ese hueco →
`RuntimeError: dictionary changed size during iteration`. `list(self._clients)` sí es atómico (copia en C,
sin bytecode intermedio). El arreglo:

- Se aplicó a **los DOS dicts**: `_loop_state` (`http.py:143`) y `_clients` (`http.py:178`). Verificado leyendo el fichero.
- No queda **ninguna** iteración de dict sin snapshot en `http.py`.
- `pop(stale, None)` además elimina la carrera del `del` (dos hilos podando el mismo loop muerto → `KeyError`).

El plan pedía replicar un precedente que estaba sutilmente roto. El ejecutor arregló el precedente en vez
de copiarlo. Correcto.

### 2. `01-02` — `is_reread` añadido fuera del artifact list → **SÓLIDA, con un defecto colateral (W-2)**

- **¿`progress.py` sigue puro?** Sí. Único import: `math` (línea 9). Sin BD, sin HTTP, sin imports del proyecto.
- **¿Es `is_reread` código muerto?** Está testeado (`test_progress.py:60-64`) y su justificación se sostiene:
  `next_progress` devuelve `int | None`, y desde `None` un llamador **no puede** distinguir «relectura de una
  serie terminada» de «sin valor del tracker». Sin `is_reread`, la Fase 5 reimplementaría la comprobación
  dentro de un endpoint — exactamente lo que el módulo existe para impedir.
- Sin call site de producción hoy, igual que `next_progress` y `effective_chapter`. Eso **es el objetivo de la
  fase** («el modelo está escrito… antes de que nada escriba una fila»), no un descuido. Deferred, no gap.
- ⚠️ **Defecto encontrado de paso (W-2):** `next_progress` declara `tracker_status` y **nunca lo lee**. La firma
  promete algo que el cuerpo no hace.

### 3. `01-03` — regla `_path` → `path` ensanchada, y `wont_watch.cover_image` en la lista blanca sin filas → **la regla, SÓLIDA; la entrada, JUSTIFICADA HOY pero con un hueco latente real (W-1)**

**La regla ensanchada es un acierto claro.** El plan decía «ninguna entrada acaba en `_local` ni `_path`».
`"path".endswith("_path")` es `False`, y las dos columnas de ruta local que existen se llaman `local_files.path`
y `library_folders.path`. La regla literal del plan habría dejado fuera **justo lo que tiene que cubrir**. El
test comprueba `endswith("path")` a secas (`test_persisted_urls.py:312`). Bien visto.

**`wont_watch.cover_image` — lo escruté a fondo, como se pidió. Es correcta hoy:**

Trazé la cadena completa. `/api/search/media` (`main.py:3905`) devuelve los resultados **crudos del proveedor**
(`media_provider.discover(...)`), sin sustitución de portadas locales — el `cover_image` es la URL del CDN remoto
(`https://s4.anilist.co/...`). `DiscoveryView` lo renderiza y `toggleWontWatch` reenvía ese mismo valor. Luego
la columna guarda URLs remotas legítimas, y la exención es correcta. Confirmado además que la tabla está vacía
en la BD real (`wont_watch: 0 filas`) — la honestidad del ejecutor es visible en la propia salida del script
(`-- wont_watch.cover_image  0 filas (exenta, pero vacía)`).

**Pero la entrada abre un hueco latente, y es exactamente el que se temía (W-1):**

`wont_watch.cover_image` es la **única** columna exenta alimentada por el **cliente**. Y el cliente tiene un
normalizador que fabrica precisamente la URL envenenada:

```typescript
// apps/desktop/src/api.ts:202-204 — corre sobre TODAS las respuestas (api.ts:249)
function normalizeAssetUrls<T>(value: T, apiUrl: string): T {
  if (typeof value === "string") {
    return (value.startsWith("/assets/") ? `${apiUrl}${value}` : value) as T;
  }
```

`${apiUrl}` es `http://127.0.0.1:<puerto>`. Si un día `/api/search/media` sirviera portadas locales
`/assets/...` — que es exactamente lo que `_local_library_items` (`main.py:781`) ya hace para la biblioteca —
el renderer las convertiría en `http://127.0.0.1:8765/assets/...`, `addWontWatch` (api.ts:446) las reenviaría
tal cual, `add_wont_watch` (main.py:3992) las guardaría verbatim, y **la guardia no las vería jamás**: la
columna está exenta por `(tabla, columna)`.

La exención es por columna; el bug es una propiedad del **valor**. Hoy sólo nos salva una propiedad de otro
módulo (que discover no localice portadas) que no está enforced en ningún sitio. Es el bug de las portadas,
esperando un cambio razonable en la Fase 3/7.

**No es un blocker** — la guardia existe, tiene dientes, cubre las columnas que nadie nombró, y corre contra
datos reales. Es una **oportunidad de endurecimiento de 3 líneas** en una frontera de confianza que este
proyecto **ya perdió una vez**. Recomendación concreta en el frontmatter (W-1).

## Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| — | — | Ninguno | — | Sin `TODO`/`FIXME`/`XXX`/`TBD`/`HACK`/`PLACEHOLDER` en los ficheros de la fase. Los `ponytail:` presentes son deliberados y nombran su techo (concurrencia 8, clamp del presupuesto). |

## Behavioral Spot-Checks (ejecutados)

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Suites de la fase | `pytest tests/test_http.py tests/test_progress.py tests/test_persisted_urls.py -q` | 44 passed in 3.83s | ✓ PASS |
| Ritmo no duerme de verdad | idem (`3.83s`) | Los tests de ritmo afirman los sleeps *solicitados*, no una carrera de reloj de pared | ✓ PASS |
| Migración v8 contra BD real | `python scripts/verify_real_db_migration.py` | `integrity_check: ok -> ok`; 7→8; recuentos idénticos; backup creado; original intacta | ✓ PASS |
| Guardia FND-05 contra BD real v8 | `python scripts/check_persisted_urls.py <copia-v8>` | exit 0; 12.610 filas remotas legítimas inspeccionadas; 0 violaciones | ✓ PASS |

Nota sobre SC-3: el ROADMAP cita 2.761 `library_entries` / 25.727 `episodes`; la BD viva tiene hoy 2.774 /
25.740 (creció 13 filas desde que se escribió el roadmap). El invariante que importa — **mismos recuentos
antes y después de migrar** — se cumple exactamente. No es un defecto; se anota para que nadie lo confunda
con uno más adelante.

## Gaps Summary

**Ninguna laguna bloqueante. El objetivo de la fase se alcanza.**

El limitador limita de verdad (y los tres bugs están cubiertos por tests con dientes probados por mutación),
el esquema v8 está migrado y verificado contra los 31,9 MB reales del usuario con backup e integridad, el
modelo de progreso está escrito, es puro y está testeado, y la guardia de URLs corre contra datos reales sin
pasar en vacío.

Quedan tres cosas para el siguiente ciclo, ninguna de las cuales invalida la fase:

1. **W-1 (la que importa):** endurecer la lista blanca con un chequeo de loopback/puerto a nivel de **valor**.
   El momento natural es planificar la Fase 3, que es cuando el reader empieza a persistir URLs de página —
   la superficie que multiplica por diez el bug que ya ocurrió.
2. **W-2:** decidir `next_progress(tracker_status)` — usarlo o quitarlo — **antes** de que la Fase 5 tenga llamadores.
3. **W-3:** marcar FND-05 como `[x]` en REQUIREMENTS.md.

---

_Verified: 2026-07-13_
_Verifier: Claude (gsd-verifier) — goal-backward, con mutation testing y ejecución contra la BD real_
