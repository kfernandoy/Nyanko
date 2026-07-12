# Deferred items — Fase 05

Hallazgos fuera del alcance del plan en el que se descubrieron.

## ~~D-I-01 — El asar empaqueta el árbol de fuentes entero, incluidos dotfiles~~ → **RESUELTO** (`d8584e2`)

- **Descubierto en:** Plan 05-02 (Tarea 3, al inspeccionar `app.asar` del instalador construido)
- **Qué era:** `electron-builder.yml` (Plan 01) no declaraba `files:`, así que el default de
  electron-builder metía en `app.asar` todo lo que hay bajo `apps/desktop`:

  ```
  \.claude\settings.local.json
  \.env.development
  \.env.development.example
  \dist\...              (build Vite obsoleto, de la era Tauri — el bueno es \out\renderer)
  \electron\main\*.ts    (los fuentes TS, incluidos los *.test.ts)
  \src\*.tsx             (los fuentes del renderer)
  \electron.vite.config.ts, \tsconfig.json, \vite.config.ts, \scripts\...
  ```

  El código que la app EJECUTA (`\out\main`, `\out\preload`, `\out\renderer`) estaba correcto: era
  peso muerto y superficie de información, no un fallo funcional. Pero un `.asar` no está cifrado
  —se extrae con un comando— y las waves 5-6 publican este instalador.

- **Investigación, hecha ANTES de tocar nada: NO había fuga.** El `.env` que contiene el
  `NYANKO_ANILIST_CLIENT_SECRET` es el del **backend**, y nunca viajó. La búsqueda del secreto
  literal por todo `release/win-unpacked` no lo encuentra en ningún sitio — ni dentro del asar ni
  dentro del sidecar de PyInstaller. Higiene, no un incidente.

- **Arreglo:** bloque `files:` en `apps/desktop/electron-builder.yml` con exclusiones **negativas**
  sobre `**/*` (`!.claude${/*}`, `!.env*`, `!electron-builder.yml`). Deliberadamente NO se reescribió
  la whitelist de lo que sí entra: restructurar eso es lo que rompe paquetes.

- **Re-verificado tras reconstruir:** asar limpio (ni `.claude` ni `.env`), layout de recursos
  intacto (sidecar, ambos bundles de extensión, icono, `app-update.yml`) y `out\main\index.js` sigue
  extrayéndose del asar con el updater dentro (8 referencias a `autoUpdater`). El arreglo entró
  **antes** de la verificación humana del Plan 02, así que el humano validó exactamente el paquete
  que se va a publicar.

## D-I-02 — El backend persiste URLs de assets con el puerto dentro → biblioteca sin portadas

- **Descubierto en:** Plan 05-06 (UAT), tras el auto-update 0.2.0 → 0.2.1. Síntoma reportado:
  «la biblioteca está media rota, no carga ningún portrait».
- **Severidad:** alta para el usuario (biblioteca visualmente inservible), **cero riesgo de datos**.
- **NO es una regresión de la Fase 5.** Es un fallo de diseño preexistente del backend que el
  engine-swap se limitó a *revelar*: `quitAndInstall` mata el sidecar, el nuevo arranca, y si coge
  otro puerto todas las portadas cacheadas mueren de golpe.

### La cadena completa (diagnosticada, no supuesta)

1. `instance.py:resolve_port()` intenta el puerto **8765** (estable, necesario para el `redirect_uri`
   de OAuth). **Si está ocupado, cae a un puerto efímero** y la app sigue funcionando.
2. `main.py:_asset_url()` compone las URLs de portada como **absolutas, con el puerto dentro**:
   `http://127.0.0.1:{settings.api_port}/assets/{provider}/{id}/cover.jpg`.
3. Esa URL absoluta se **persiste** en `media_details_cache.cover_image_local` /
   `.banner_image_local`.
4. `database.py:1607` la devuelve **tal cual** a la grid, y la **prefiere** sobre la URL remota del
   CDN: `row["cover_image_local"] or row["cover_image"]`. Si la local está muerta, NO cae al CDN.
5. `database.py:1503` usa `COALESCE(existente, nuevo)` al reingestar → **una vez escrita, la URL no
   se actualiza nunca**. No hay auto-curación.

**Resultado:** cualquier arranque del sidecar en un puerto distinto al que se cacheó deja la
biblioteca sin una sola portada, de forma permanente y silenciosa.

### Qué lo disparó aquí

Dos `scripts\dev.py` del propio usuario tenían ocupado el 8765 (el «múltiples dev.py = caos» ya
conocido). El sidecar de producción llevaba varias sesiones cayendo a puertos efímeros — se ve en
`sidecar.log`: 56181, 58189, 55297, 63267, 51874. En la BD había **3.874 URLs** repartidas entre dos
puertos muertos (56181 y 55297).

### Qué se hizo (reparación de DATOS, no de diseño)

- Matados los `dev.py` → 8765 libre → el sidecar vuelve a cogerlo (verificado: `port` = 8765).
- Reescritas las 3.874 URLs al puerto vivo. `integrity_check: ok`. Backup previo de la BD en
  `~/Desktop/nyanko-db-antes-de-reparar-portadas.sqlite3`.
- Check ejecutable que falla si vuelve a pasar:
  `scratchpad/check_stale_asset_ports.py` (falló con 3.874 antes, pasa con 0 después).

### Arreglo REAL, pendiente para 0.3 (fuera de alcance: 0.2 es engine-swap puro, el backend no se toca)

El bug de fondo sigue vivo: basta que algo ocupe el 8765 para que vuelva a envenenarse. Opciones,
en orden de preferencia:

1. **No persistir el host:puerto.** Guardar una ruta relativa (`/assets/anilist/21/cover.jpg`) y que
   el renderer la componga contra la base de API que ya resuelve dinámicamente. Elimina la clase de
   bug entera.
2. Si hay que seguir devolviendo absolutas, **recalcularlas al leer** (como ya hace
   `main.py:401` con `_local_asset_url(...) or ...`) en TODOS los caminos, no solo en algunos.
3. Como mínimo, que un `cover_image_local` inalcanzable **caiga al `cover_image` remoto** en vez de
   dejar el hueco.

## D-I-03 — El rate limit de AniList que creemos tener (90) ya no es el que nos dan (30)

- **Descubierto en:** Plan 05-06 (2026-07-12), depurando el backfill clavado en 0/1811.
- **Severidad:** baja **hoy**, trampa latente **mañana**.

`anilist.py:482` construye el cliente así:

```python
_client = RateLimitedClient(requests_per_minute=90)
```

Ese 90 era el límite real de AniList cuando se escribió. **Hoy su cabecera `X-RateLimit-Limit`
responde `30`.** Nuestro limitador cree tener 3x el presupuesto que tiene.

**Por qué no está mordiendo ahora mismo:** el backfill es secuencial y va a ~1 req cada 2 s (≈30
req/min), justo por debajo del límite real — por pura casualidad, no por diseño. El número que
gobierna el ritmo no es el `requests_per_minute`, es el ida y vuelta de la red.

**Por qué es una trampa:** en cuanto algo emita **ráfagas** (paralelizar el backfill, un botón de
«refrescar todo», cualquier concurrencia), el limitador dejará pasar hasta 90 y AniList devolverá
429 a partir del 31. El limitador existe justo para que eso no pase, y con este valor **no protege
de nada**.

**Arreglo, a 0.3 con el resto del backend:** o bajar el literal a 30, o —mejor— **leer
`X-RateLimit-Limit` de la respuesta y ajustarse**, que es lo único que sobrevive al siguiente cambio
unilateral de AniList. Este plan ya vio a AniList degradar su latencia ~6x sin avisar; el límite es
igual de suyo y de cambiante.
