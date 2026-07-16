---
status: testing
phase: 03-page-pipe-lectura-local-la-piedra-angular
source:
  - 03-01-SUMMARY.md
  - 03-02-SUMMARY.md
  - 03-03-SUMMARY.md
  - 03-04-SUMMARY.md
  - 03-05-SUMMARY.md
  - 03-06-SUMMARY.md
  - 03-07-SUMMARY.md
started: 2026-07-16
updated: 2026-07-16
---

## Current Test

number: 1
name: La transicion encadena capitulos y emite UNA fila de reading_events
expected: |
  Al pasar de pagina en la ULTIMA pagina de un capitulo aparece una pantalla de transicion
  ofreciendo el capitulo siguiente; al continuar, se abre. Y en `reading_events` de la SQLite
  aparece UNA sola fila para ese capitulo, no varias.
awaiting: user response

## Tests

### 1. La transicion encadena capitulos y emite UNA fila de reading_events
requirement: RD-06
source: 03-06 D4
expected: |
  Pasar de pagina en la ULTIMA pagina abre la pantalla de transicion con el capitulo
  siguiente; al continuar, se abre ese capitulo. `reading_events` gana UNA fila para el
  capitulo terminado (no dos, aunque vuelvas atras y adelante).
result: pending

### 2. La CSP no rompe nada visible (portadas, HMR, splash)
requirement: RD-09 / Seam G
source: 03-07 D3
expected: |
  La fase 03 introdujo la PRIMERA CSP de la app, y su plan avisaba de que la CSP literal del
  ROADMAP borraba las portadas de media app. Se escribio corregida (con `https:` y
  `ws://127.0.0.1:*`), y `test:csp` (6/6) comprueba la CADENA, pero que las portadas se VEAN
  no lo comprueba nadie. Concretamente: Descubrir / Temporadas / Busqueda muestran portadas y
  el avatar se ve; `npm run dev` no revienta por el preambulo inline de React Refresh; y los
  botones del splash (Reintentar / Abrir logs / Salir) responden.
result: pending

## Auto-covered (29/31 — no se preguntan)

Cubiertos de forma determinista por tests que el orquestador ejecuto FUERA del sandbox de Codex
(CODEX-RULES regla 5). Ver el bloque `coverage:` de cada SUMMARY.

| Plan | Auto | Como |
|------|------|------|
| 03-01 | 4/4 | pytest (contrato v2, CBZ/ZIP, ComicInfo, orden natural) |
| 03-02 | 6/6 | pytest (esquema v9 + migracion con backup, prefs, progreso, eventos, FND-05) |
| 03-03 | 4/4 | pytest (ruta antes del mount, 8 variantes de traversal, URLs relativas) |
| 03-04 | 6/6 | pytest (API `/api/manga/*`, aislamiento por serie, 404/415/429/502/503, WR-06) |
| 03-05 | 3/3 | tsc + **UAT manual del usuario** (navega raices, series y capitulos) |
| 03-06 | 2/4 | `test:reader` 4/4 + medicion en Electron real (5 paginas montadas) + **UAT manual** |
| 03-07 | 3/4 | `test:reader` + `test:reader-rss` (RD-09: 136-166 MB vs techo 500) + `test:csp` + tsc |

Suite completa: **461 passed**. Los 13 tests citados por 03-02/03/04 re-ejecutados por nombre: 22 passed.

## Gaps

<!-- Se rellena si algun test falla -->

## Notes

**Esta UAT NO empieza de cero.** El usuario ya hizo una UAT manual completa el 2026-07-16 y
encontro **9 defectos**, todos cerrados: 5 en la primera vuelta (CBR — que no era bug sino una
decision de licencia ya escrita; el escaneo de anime al anadir manga; el ajuste «alto» que
cortaba; los saltos de scroll en vertical; el contador invisible), 3 de UX en la segunda (no se
podia ver la parte que sobra en «ancho»/«original»; ~92px de hueco en el lomo; el zoom no bajaba
del 100%) y 1 regresion que introdujo el arreglo del #2. Preguntar de nuevo por lo ya confirmado
seria interrogatorio, no verificacion.

Los `status:` de coverage venian con tres vocabularios invalidos (`deferred`, `passing`,
`failing`) porque Codex no puede ejecutar nada y los dejaba abiertos a proposito. Cerrados aqui
con resultados reales — es literalmente el trabajo que CODEX-RULES regla 5 asigna al orquestador
y que no se habia hecho. **`03-07` D2 decia `failing` con «RD-09 no se cumple»**: era cierto por
la manana y hoy es falso.

Los DOS que quedan son los unicos que nadie ha mirado nunca, y ninguno es cosmetico:
- **RD-06 / D-15**: el evento de lectura nace ANTES que su consumidor, para que la Fase 5
  encuentre el trigger del sync ya persistido. Si no emite, la Fase 5 arranca sobre una tabla
  vacia y el fallo aparece alli, lejos de su causa.
- **Seam G**: la CSP no tiene otro dueno en el ROADMAP. Si borra las portadas, se descubre en
  produccion.
