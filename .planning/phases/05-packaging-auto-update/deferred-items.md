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
