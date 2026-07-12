# Deferred items — Fase 05

Hallazgos fuera del alcance del plan en el que se descubrieron. NO se arreglaron.

## D-I-01 — El asar empaqueta el árbol de fuentes entero, incluidos dotfiles

- **Descubierto en:** Plan 05-02 (Tarea 3, al inspeccionar `app.asar` del instalador construido)
- **Qué es:** `electron-builder.yml` (Plan 01) no declara `files:`, así que el default de
  electron-builder mete en `app.asar` todo lo que no esté excluido. Listado real del paquete:

  ```
  \.claude\settings.local.json
  \.env.development
  \.env.development.example
  \dist\...              (build Vite obsoleto, de la era Tauri — el bueno es \out\renderer)
  \electron\main\*.ts    (los fuentes TS, incluidos los *.test.ts)
  \src\*.tsx             (los fuentes del renderer)
  \electron.vite.config.ts, \tsconfig.json, \vite.config.ts, \scripts\...
  ```

  El código que la app EJECUTA (`\out\main`, `\out\preload`, `\out\renderer`) está correcto; esto
  es peso muerto y superficie de información, no un fallo funcional.

- **Por qué importa:** `.env.development` y `.claude/settings.local.json` viajan dentro de un
  paquete que se distribuye a usuarios. Un `.asar` no está cifrado: se extrae con `npx asar
  extract` en un comando. Si alguno de esos ficheros contiene algo que no deba salir de la
  máquina de desarrollo, ya está publicado. **No pude leer `.env.development` para comprobarlo:
  mis permisos deniegan esa ruta, y no lo eludí.** Alguien con acceso debe mirarlo.
- **Por qué NO se arregló aquí:** es la config de empaquetado del Plan 01
  (`apps/desktop/electron-builder.yml`); ninguno de los ficheros de este plan la toca. Tocarla
  habría cambiado el instalador que este mismo plan tiene que verificar en su checkpoint.
- **Arreglo:** un bloque `files:` en `electron-builder.yml` que liste solo `out/**` (+ `package.json`),
  y reconstruir. Debería además adelgazar bastante el paquete.
