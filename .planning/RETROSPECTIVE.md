# Retrospective — Nyanko

Living document. Una sección por milestone, más tendencias al final.

## Milestone: v0.2 — Tauri → Electron

**Shipped:** 2026-07-13
**Phases:** 5 | **Plans:** 15 | **Commits:** 103 | **Timeline:** 2026-07-09 → 2026-07-13 (5 días)

### What Was Built

El shell de escritorio pasó de Tauri 2 (Rust) a Electron sin perder un byte de biblioteca: scaffold
electron-vite con `userData` clavado al identifier de Tauri, ciclo de vida del sidecar Python con
readiness gate, frontera nativa única (`native.ts`, 20 ops) que borró todos los `@tauri-apps/*`,
paridad de features nativas (tray, prefs, RPC, autostart…), y empaquetado NSIS + auto-update por
electron-updater — con un puente minisign para que el parque 0.1.15 ya instalado pudiera llegar solo.

### What Worked

- **El self-check bidireccional de la frontera nativa.** `native.test.ts` compara `NATIVE_OPS` contra
  `native` en ambas direcciones. La Fase 3 dejó 10 stubs deliberados; el self-check es lo que
  garantizó que la Fase 4/5 los implementara todos en vez de que se colaran a producción como no-ops
  silenciosos. Coste: ~20 líneas de test. Es la mejor relación valor/esfuerzo del milestone.

- **Gates humanos sobre instalaciones reales, no sobre código.** El auto-update y la migración desde
  Tauri no se dieron por buenos por inspección: se ejecutaron sobre la máquina real, con la
  biblioteca real, y se midió el resultado (md5 del sqlite, conteos por tabla, bytes descargados).
  Es lo que convirtió «debería funcionar» en «funcionó».

- **El experimento D-02 antes de escribir la rama de migración.** Se midió sobre una 0.1.15 real que
  el uninstall silencioso de Tauri NO borra `%APPDATA%`, y solo entonces se autorizó ejecutar ese
  binario desde el instalador. Medir primero, codificar después.

- **El audit cruzado de milestone.** Encontró B-1, que ningún gate por fase podía encontrar. Sin ese
  paso, v0.2 se habría archivado con el instalador silenciosamente roto.

### What Was Inefficient

- **Las verificaciones por fase dieron una falsa sensación de seguridad.** Cinco fases `passed`, y
  aun así el instalador estaba roto. El fallo vivía en la **costura** entre la Fase 2 (matar el
  sidecar porque bloquea ficheros) y la Fase 5 (empaquetar): el arreglo de una desactivó la
  protección de la otra. Ninguna fase era incorrecta por separado. El audit cruzado no debería ser
  el último paso opcional — debería correr en cuanto dos fases se tocan.

- **Los gates pasaron porque la máquina es rápida.** La carrera entre `quitAndInstall()` y el
  `app.quit()` diferido la ganaba el update. Un gate que pasa por suerte es un gate que miente.

- **Documentación que se desincronizó del código.** Cuatro requisitos se quedaron en `Pending` con
  sus fases verificadas; STATE.md listaba como *deferred* algo ya resuelto; las SUMMARY afirmaban
  releases que se habían borrado. Nada de esto rompió código, pero el audit tuvo que gastar esfuerzo
  distinguiendo drift documental de gaps reales.

- **Features de 0.3 filtrándose en el árbol antes de cerrar 0.2.** La regla dura era «0.2 es
  engine-swap puro». Se commitearon manga, discovery y ajustes en modal mientras el milestone seguía
  abierto. No hizo daño, pero borra la línea que hacía la migración auditable.

### Patterns Established

- **Frontera nativa con manifiesto + self-check bidireccional.** Cualquier op nativa nueva debe estar
  en `NATIVE_OPS` o el test falla. Cero accesos a `window.nyanko` fuera de `native.ts`.
- **`ponytail:`-tagged stubs.** Un stub deliberado se marca, se cuenta y se cierra en la fase
  siguiente. No es deuda si está inventariada.
- **Un gate humano se define por lo que hay que OBSERVAR, no por lo que hay que ejecutar.** El ítem
  del EULA se arrastró tres instalaciones porque cada gate preguntaba por otra cosa.
- **Los hechos operativos caros se miden y se anotan como literales.** Las claves de registro del
  uninstaller de Tauri, el `_?=` del ExecWait, el `!ifmacrondef` — todos llevan un comentario que
  explica por qué NO se pueden «simplificar». Ese comentario es el que impide la próxima regresión.

### Key Lessons

1. **Una fase verificada no es una fase segura.** Los bugs viven en las costuras entre fases
   correctas. Verificar por fase es necesario y no es suficiente.
2. **Compilar no es probar.** El NSIS compilaba con la protección desactivada. La única prueba de
   B-1 fue abrir la app y correr el instalador.
3. **Cuando un hook de un framework parece aditivo, léelo.** `customCheckAppRunning` suena a «añade
   tu check»; es «reemplaza el mío».
4. **Un supuesto del PROJECT.md puede ser falso y costarte el parque entero.** «Un solo usuario, no
   hace falta puente» habría dejado varada en silencio a toda la base 0.1.15.

### Cost Observations

- 103 commits en 5 días, 122 ficheros, +19.540/−9.605.
- Cuatro releases publicados (0.2.0 → 0.2.3), dos de ellos borrados a propósito tras servir su
  salto de auto-update.
- El bug más caro del milestone (B-1) se encontró **después** de que las 5 fases pasaran, y costó
  ~2 líneas de NSIS arreglarlo.

## Cross-Milestone Trends

| Milestone | Fases | Planes | Commits | Días | Bugs post-verificación |
|-----------|-------|--------|---------|------|------------------------|
| v0.2 Tauri → Electron | 5 | 15 | 103 | 5 | 1 blocker (B-1), encontrado por audit cruzado |

**A vigilar en 0.3:** si el próximo milestone también encuentra su blocker en el audit cruzado y no
en los gates por fase, el problema no es la suerte — es que los gates por fase no miran las costuras.
