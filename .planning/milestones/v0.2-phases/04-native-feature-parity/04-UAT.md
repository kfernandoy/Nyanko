---
status: complete
phase: 04-native-feature-parity
source: [04-VERIFICATION.md]
started: 2026-07-11T14:20:00Z
updated: 2026-07-11T15:05:00Z
---

## Current Test

[testing complete]

## Tests

### 1. Bandeja — menú y doble-click
expected: Menú con Mostrar / Ocultar / Pausar detección / Salir (en español); doble-click restaura y enfoca la ventana
result: pass

### 2. Bandeja — toggle de detección
expected: Con el backend arriba, "Pausar detección" hace POST a /api/detection/pause, la etiqueta pasa a "Reanudar detección" y el renderer refleja la pausa. Si el POST falla, el estado NO cambia
result: pass

### 3. Prefs de ventana — close-to-tray y minimize-to-tray
expected: Con ambos activos, cerrar oculta a bandeja (proceso vivo) y minimizar oculta; "Mostrar" restaura; "Salir" hace quit limpio sin dejar nyanko-api.exe huérfano
result: pass

### 4. Start-minimized
expected: Con el ajuste activo (o lanzando con --minimized), la app arranca sin ventana visible, solo icono de bandeja
result: pass

### 5. Titlebar frameless
expected: Los botones minimizar / maximizar / cerrar responden y la barra arrastra la ventana
result: pass
note: "Falló en la primera pasada (botones OK, arrastre no). Causa raíz: la barra seguía con data-tauri-drag-region, atributo de Tauri que Electron ignora; faltaba -webkit-app-region. Arreglado en 234e576 y re-verificado en vivo."

### 6. Discord Rich Presence
expected: Con Discord abierto, reproducir muestra presencia con details/state/elapsed; cerrar Discord a mitad de sesión NO tumba la app; parar la reproducción limpia la presencia
result: pass

### 7. Single-instance
expected: Lanzar un segundo ejecutable con la app corriendo — el segundo sale y la ventana viva se muestra y enfoca (incluso si estaba en bandeja)
result: pass

### 8. Autostart
expected: Activar el toggle registra el login item de Windows con --minimized; desactivarlo lo elimina
result: pass

## Summary

total: 8
passed: 8
issues: 0
pending: 0
skipped: 0
blocked: 0

## Gaps

- truth: "La barra de título frameless arrastra la ventana"
  status: resolved
  reason: "User reported: los botones funcionan, arrastrar no"
  root_cause: "data-tauri-drag-region sobrevivió al purgado de Tauri de Fase 3 (buscaba imports, no atributos HTML). Electron arrastra por CSS (-webkit-app-region), que no existía en el proyecto."
  fix: 234e576
  severity: major
  test: 5
