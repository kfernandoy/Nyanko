---
status: testing
phase: 04-native-feature-parity
source: [04-VERIFICATION.md]
started: 2026-07-11T14:20:00Z
updated: 2026-07-11T14:20:00Z
---

## Current Test

number: 1
name: Bandeja — menú y doble-click
expected: |
  Click derecho en el icono de bandeja abre un menú con exactamente: Mostrar, Ocultar,
  Pausar detección, separador, Salir. Doble-click izquierdo muestra la ventana, la
  restaura si estaba minimizada y le da el foco.
awaiting: user response

## Tests

### 1. Bandeja — menú y doble-click
expected: Menú con Mostrar / Ocultar / Pausar detección / Salir (en español); doble-click restaura y enfoca la ventana
result: [pending]

### 2. Bandeja — toggle de detección
expected: Con el backend arriba, "Pausar detección" hace POST a /api/detection/pause, la etiqueta pasa a "Reanudar detección" y el renderer refleja la pausa. Si el POST falla, el estado NO cambia
result: [pending]

### 3. Prefs de ventana — close-to-tray y minimize-to-tray
expected: Con ambos activos, cerrar oculta a bandeja (proceso vivo) y minimizar oculta; "Mostrar" restaura; "Salir" hace quit limpio sin dejar nyanko-api.exe huérfano
result: [pending]

### 4. Start-minimized
expected: Con el ajuste activo (o lanzando con --minimized), la app arranca sin ventana visible, solo icono de bandeja
result: [pending]

### 5. Titlebar frameless
expected: Los botones minimizar / maximizar / cerrar responden y la barra arrastra la ventana
result: [pending]

### 6. Discord Rich Presence
expected: Con Discord abierto, reproducir muestra presencia con details/state/elapsed; cerrar Discord a mitad de sesión NO tumba la app; parar la reproducción limpia la presencia
result: [pending]

### 7. Single-instance
expected: Lanzar un segundo ejecutable con la app corriendo — el segundo sale y la ventana viva se muestra y enfoca (incluso si estaba en bandeja)
result: [pending]

### 8. Autostart
expected: Activar el toggle registra el login item de Windows con --minimized; desactivarlo lo elimina
result: [pending]

## Summary

total: 8
passed: 0
issues: 0
pending: 8
skipped: 0
blocked: 0

## Gaps
