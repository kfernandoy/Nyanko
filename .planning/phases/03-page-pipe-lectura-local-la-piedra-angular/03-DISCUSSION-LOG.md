# Phase 3: Page pipe + lectura local — Discussion Log

**Date:** 2026-07-14
**Participants:** kfern + Claude
**Purpose:** registro humano de la discusión. Los agentes downstream leen `03-CONTEXT.md`, no esto.

---

## Áreas presentadas

Las cuatro seleccionadas por el usuario (todas):

1. El camino de los bytes
2. Memoria y el número de RSS
3. Qué se recuerda por serie
4. El evento «capítulo terminado»

No se presentaron como categorías genéricas: cada una era una bifurcación real que cambia el
resultado, encontrada leyendo el código antes de preguntar.

---

## 1. El camino de los bytes

**El hallazgo que cambió las opciones:** el mount `/assets` sirve **solo** `%APPDATA%\...\assets`,
pero los CBZ y las carpetas del usuario viven en sus discos. El ROADMAP había previsto extraer todo a
`assets_dir/_stream/` y declarar un techo (limpiar al arrancar y al cerrar capítulo). Leyendo
`api.ts:202` apareció una tercera vía que el ROADMAP no contempló: `normalizeAssetUrls` reescribe
**cualquier** string que empiece por `/assets`, no solo ficheros del mount.

| Opción | Coste |
|---|---|
| **Ruta dinámica bajo `/assets`, sin copiar** ← ELEGIDA | Hay que registrarla antes del mount |
| `_stream/` para todo (lo del ROADMAP) | Duplica en disco lo que ya está en disco; latencia al abrir; caché que limpiar |
| Híbrido (extraer solo el CBZ) | Dos caminos, dos tests, y la limpieza igual |

**Elegido:** ruta dinámica. `FileResponse` para carpetas, `StreamingResponse(zipfile.open())` para
CBZ. **Sin `_stream/`, sin caché, sin limpieza.** Anula el «Techo declarado» del ROADMAP — y lo anula
hacia abajo: sin caché no existe el bug de «la caché se come el SSD».

**Lo que salió de aquí y no estaba en la pregunta:** el mount `/assets` es **no autenticado**. Una
ruta bajo ese prefijo que aceptara paths sería lectura arbitraria de disco desde el renderer. Queda
fijado que el endpoint acepta un ID opaco resuelto **por la fuente** (que ya valida contención), nunca
una ruta. Test de traversal obligatorio.

---

## 2. Memoria y el número de RSS

Opciones: ventana ±2 / ±3 / ±5, con techos de 500 MB / 700 MB / 1 GB.

**Elegido:** **±2 páginas, RSS < 500 MB** tras 200 páginas ida y vuelta.

El razonamiento que se aceptó: un techo de 1 GB casi no es un techo — cabe un leak entero dentro. RD-09
existe para que el número **apriete**, no para que quepa lo que sea.

---

## 3. Qué se recuerda por serie

Opciones: dos tablas / una tabla única por serie / filas en `settings`.

**Elegido:** **dos tablas** (`reader_prefs` por serie, `reader_progress` por capítulo), schema v9.

Lo que descartó la tabla única: RD-05 dice «reanuda **un** capítulo», no «el último capítulo». Con una
sola tabla por serie, volver a un capítulo anterior te deja en la página 1.
Lo que descartó `settings`: la guardia FND-05 introspecciona el esquema; un JSON opaco dentro de una
tabla key/value se le escapa.

Zoom y paneo **no** se persisten (transitorios). RTL es el defecto.

---

## 4. El evento «capítulo terminado»

Opciones: tabla propia calcada de `playback_events` / reutilizar `playback_events` / señal efímera.

**Elegido:** **tabla propia `reading_events`**, con `chapter REAL`.

Reutilizar `playback_events` parecía lo perezoso, pero su `episode` es `INTEGER` y el modelo de
progreso de la Fase 1 es `REAL` a propósito (FND-04). Un capítulo `12.5` se perdería — y ese es
exactamente el punto donde se corrompe el tracker. La señal efímera se descartó por lo contrario: la
Fase 5 tendría que retrofittear la persistencia, que es el tipo de costura que el ROADMAP pone esta
fase primero para evitar.

Queda escrito que en esta fase **nadie lee la fila**. Eso es el diseño.

---

## A discreción de Claude (no se preguntó)

- CBZ/ZIP + `ComicInfo.xml` en `LocalArchiveSource` (hoy solo lee carpetas) — `zipfile` de stdlib.
- CBR/RAR: se detecta y se dice «conviértelo a CBZ» (decisión de licencia ya tomada en REQUIREMENTS).
- Entrada en la UI: vista de lectura a pantalla completa. El ROADMAP marca `UI hint: yes`.
- CSP en la ventana principal **y en la splash** (las dos declaran las mismas `webPreferences`).

## Ideas aparcadas

- LRU / caché de lectura en disco: solo con una medición delante.
- CBR/RAR, EPUB/PDF: v0.3.x+ / v0.4+.
- WR-01 y WR-08 (deuda de la Fase 2, 4 líneas cada una): de paso, o Fase 9.
