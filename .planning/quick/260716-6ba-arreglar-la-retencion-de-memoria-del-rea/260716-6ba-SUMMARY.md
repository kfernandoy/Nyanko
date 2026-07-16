---
quick_id: 260716-6ba
status: complete
date: 2026-07-16
requirements: [RD-09]
commits:
  - abc7b6e fix(260716-6ba): mount only the visible group in paged reader mode
  - 3c9c4b3 fix(260716-6ba): drop the preload rules that laid out pages at intrinsic size
---

# Quick 260716-6ba — RD-09: el reader paginado deja de retener 4 bitmaps a 2000x3000

## Qué lo motivó

RD-09 estaba **REPROBADO con evidencia medida**: 621 MB (pico 691 MB) contra un techo de 500 MB, y
era el último blocker de la Fase 03. La causa raíz la había aislado CR-02: las 4 páginas de preload
se maquetaban a resolución intrínseca porque su CSS (`max-width: none; max-height: none`) les quitaba
toda restricción de tamaño. Estaban fuera del lienzo (`left: -100000px`), no ocultas — así que
Chromium las maquetaba, las decodificaba y pagaba el bitmap entero de cada una.

El diagnóstico era falsable y se comprobó antes de tocar nada: con ventana=1 el mismo harness medía
153 MB. La medición respondía al tamaño de la ventana, luego medía bitmaps reales.

## El arreglo

**Tarea 1 — `ReaderView.tsx`:** en la rama paginada, `ventana.map` pasa a `paginasVisibles.map`. El
DOM monta exactamente el grupo visible (1 página, o 2 con doble página). Al ser todo visible por
construcción desaparecen la variable `visible`, el ternario de className y el `aria-hidden`.

Los vecinos de la ventana se calientan con un `useEffect` nuevo que hace `fetch` bajo un
`AbortController`, sin crear elemento. **Sin elemento vivo no hay layout, ni decode, ni bitmap.**
El `abort()` en la limpieza es lo que impide que pasar página apile peticiones capítulo abajo.

**Tarea 2 — `styles.css`:** borradas las dos reglas de la clase de preload (ya no las referencia
nadie) y reescrito el comentario de cabecera del bloque del reader, que describía un mecanismo
recién borrado — un comentario que miente es peor que ninguno.

La rama vertical **no se tocó**: sigue montando la ventana entera (`indicesVivos`), porque el scroll
continuo necesita los vecinos y sus reglas ya acotan cada imagen a su slot.

## Verificación — el número medido

```
RSS renderer: 161.36 MB (pico 244.07 MB; techo 500 MB) -> OK
```

Exit 0. Medido tras `npm run build` (obligatorio: el harness carga `out/renderer/index.html`, el
bundle construido — medir sin reconstruir mide el código viejo).

| | Antes | Después | Techo |
|---|---|---|---|
| RSS final | 621 MB | **161.36 MB** | 500 MB |
| Pico | 691 MB | **244.07 MB** | 500 MB |

**La predicción falsable del plan se cumplió.** Decía que debía aterrizar cerca de la medición con
ventana=1 (~153 MB final, ~221 MB de pico), porque tras el arreglo el DOM paginado tiene exactamente
una página. Medido: 161.36 / 244.07. Los ~8 MB de más sobre el final y ~23 MB sobre el pico son
consistentes con las 4 entradas de caché HTTP calentadas sin bitmap. No hay nada que sugiera que
quede otro retenedor.

El gate **no se aflojó**: `MAX_LIVE_PAGES` sigue en 5 y `TECHO_RSS_MB` sigue en 500. El número baja
porque el reader retiene menos.

Resto de gates:
- `npm run test:reader` — 4/4 pass.
- `npm run check` (`tsc --noEmit`) — limpio.
- `npm run build` — limpio.

## Pendiente de verificación humana (NO comprobado)

La **comprobación manual de los tres modos con un capítulo real** queda para el usuario. El harness
solo cubre el modo paginado (espera `.reader-page--visible img` y navega con PageDown/PageUp), y la
03-06 entregó tres modos. Falta confirmar a mano:

- **rtl / ltr:** que se pase de página y las flechas respeten el sentido de lectura.
- **vertical:** que el scroll continuo siga mostrando los vecinos, sin huecos en blanco.
- **doble página en rtl:** deben verse DOS páginas a la vez, no una.

## Honestidad sobre el alcance del calentado

Que Chromium reutilice de verdad la entrada calentada para el `<img>` posterior **no está probado** y
no lo mide ningún gate. No se afirma aquí ni en el código.

No importa para RD-09: CR-02 ya demostró que el preload de hoy pagaba memoria máxima por **cero**
reutilización de decode, así que el calentado es en el peor caso neutro respecto a lo que había — y
quita 460 MB por el camino. Si algún día se quiere cobrar de verdad esa reutilización, hay que
medirla, no suponerla.

## Alcance

Diff acotado a `apps/desktop/src/ReaderView.tsx` y `apps/desktop/src/styles.css`.
`readerWindow.ts` sin cambios. Sin dependencias npm nuevas.

## Self-check

- Ficheros modificados existen y están commiteados: `abc7b6e`, `3c9c4b3`. Verificado con `git log`.
- Ambos commits sin borrados de ficheros (`git diff --diff-filter=D` vacío).
- Gates automatizados: ejecutados de verdad, números pegados literales arriba.
- UAT manual de los tres modos: **pendiente** — no marcado como hecho.
