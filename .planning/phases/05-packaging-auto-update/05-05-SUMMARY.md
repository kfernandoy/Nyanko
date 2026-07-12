---
phase: 05-packaging-auto-update
plan: 05
subsystem: packaging
tags: [icon, tray, resources-path, compat-paths, packaging]
status: complete

requires:
  - "extraResources `build/icon.png` → `resources/icon.png` (Plan 01, electron-builder.yml)"
  - "compat-paths.ts — módulo Electron-free con self-check bajo Node plano (Fase 2)"
provides:
  - "iconPath(isPackaged, resourcesPath, mainDir) en electron/main/compat-paths.ts — resolución única del icono"
  - "cierre del riesgo diferido de la Fase 4 (icono colgante en el paquete)"
affects:
  - "Plan 02 (updater): su checkpoint sobre el NSIS instalado es donde se confirma VISUALMENTE que el gatito sale en la bandeja"

tech-stack:
  added: []
  patterns:
    - "Resolución de recursos empaquetados por process.resourcesPath — misma forma que resolveSidecarExe()"
    - "Helpers puros con isPackaged/resourcesPath como parámetros: compat-paths.ts sigue Electron-free y testeable bajo Node plano"

key-files:
  created: []
  modified:
    - apps/desktop/electron/main/compat-paths.ts
    - apps/desktop/electron/main/compat-paths.test.ts
    - apps/desktop/electron/main/index.ts
    - apps/desktop/electron/main/tray.ts

decisions:
  - "La rama por isPackaged es deliberada: a diferencia del sidecar (solo prod), el icono se necesita en dev Y en el paquete"
  - "iconPath recibe isPackaged/resourcesPath como parámetros en vez de importar `app`: mantiene compat-paths.ts Electron-free, que es lo que permite su self-check sin mockear electron"

metrics:
  duration: ~12 min
  completed: 2026-07-12
  tasks_completed: 1
  files_created: 0
  files_modified: 4
---

# Phase 5 Plan 05: Icono resuelto por `process.resourcesPath` — Summary

El icono de la ventana y el de la bandeja se resuelven ahora por `iconPath()`, que apunta a
`resources/icon.png` bajo empaquetado y a `build/icon.png` en dev — cerrando el riesgo diferido de
la Fase 4, donde ambos call sites colgaban de una ruta que **no existe dentro del NSIS**.

## Qué se construyó

Una función pura de tres líneas en `compat-paths.ts`:

```ts
export function iconPath(isPackaged: boolean, resourcesPath: string, mainDir: string): string {
  if (isPackaged) return join(resourcesPath, "icon.png");
  return join(mainDir, "..", "..", "build", "icon.png"); // dev: out/main → apps/desktop
}
```

Los dos call sites (`index.ts:40` en el `BrowserWindow`, `tray.ts:69` en el
`nativeImage.createFromPath`) pasan a llamarla con `(app.isPackaged, process.resourcesPath, __dirname)`.
Sus `join(...)` literales a `../../build/icon.png` quedan borrados: `build/` es el `buildResources`
de electron-builder y **no viaja dentro de la app**, así que en el instalado esas rutas apuntaban a
nada.

## Por qué era invisible

`nativeImage.createFromPath()` sobre una ruta inexistente **no lanza**: devuelve una imagen vacía.
Por eso el bug sobrevivió una fase entera sin un solo error ni línea de log — la bandeja
simplemente habría salido sin gatito. Es exactamente el fallo silencioso que el self-check nuevo
convierte en un test rojo.

## Consumir lo que ya existe, no duplicarlo

El Plan 01 ya había puesto `build/icon.png → resources/icon.png` en `extraResources`. Este plan **no
añade una segunda copia**: solo cablea el código a la que ya está en el paquete. Verificado en disco
que ambas ramas apuntan a un fichero real y al mismo (33.841 B):

| Rama | Ruta resuelta | En disco |
|---|---|---|
| dev | `apps/desktop/build/icon.png` | 33.841 B |
| empaquetado | `release/win-unpacked/resources/icon.png` | 33.841 B |

## Verificación (ejecutada, no asumida)

TDD real: el test se escribió primero y **falló** (commit `8733f40`, RED — el import de `iconPath`
no resolvía), y pasó tras la implementación (`8266f3e`, GREEN).

El bloque `<automated>` del plan, corrido tal cual:

```
test:datadir OK
tsc OK
ICON OK
```

- `npm run test:datadir` → **5/5**, con los dos asserts nuevos (rama empaquetada y rama dev).
- `npx tsc --noEmit` → 0.
- Gate negativo: ni `index.ts` ni `tray.ts` contienen ya la subcadena `build/icon.png`; ambos
  llaman a `iconPath(`. `compat-paths.ts` exporta `iconPath` y **sigue sin importar nada de
  `electron`** (el módulo es Electron-free por contrato — su test corre bajo Node plano).

**Lo que este plan NO verifica:** que el gatito salga de verdad en la bandeja del NSIS instalado.
Eso es confirmación visual y la hace el checkpoint del **Plan 02** (wave 3), que ya instala el
paquete — no se montó una segunda instalación de 131 MB solo para mirar un icono. El self-check
prueba la resolución de rutas; el ojo humano prueba el píxel.

## Deviations from Plan

Ninguna. El plan se ejecutó exactamente como estaba escrito: una tarea, un helper puro, dos call
sites recableados. No hizo falta empaquetar, así que tampoco se tropezó con el hazard del `EPERM`
por sesión de dev viva que documentó el Plan 01.

## Known Stubs

Ninguno.

## Self-Check: PASSED

Ficheros declarados: existen. Commits declarados (`8733f40`, `8266f3e`): existen.
