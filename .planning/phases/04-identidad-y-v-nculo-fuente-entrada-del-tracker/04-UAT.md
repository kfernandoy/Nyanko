---
status: testing
phase: 04-identidad-y-v-nculo-fuente-entrada-del-tracker
source: [04-VERIFICATION.md]
started: 2026-07-17T15:14:42Z
updated: 2026-07-17T15:14:42Z
---

## Current Test

number: 1
name: Pulsar el boton de vincular de una serie sin vinculo (MangaLibraryView)
expected: |
  Se abre el panel con la propuesta, un porcentaje de confianza visible y hasta 5 alternativas; la vista NO navega dentro de la carpeta.
awaiting: user response

## Tests

### 1. Pulsar el boton de vincular de una serie sin vinculo (MangaLibraryView)
expected: Se abre el panel con la propuesta, un porcentaje de confianza visible y hasta 5 alternativas; la vista NO navega dentro de la carpeta.
result: [pending]

### 2. Con teclado (Tab), la fila de una serie ofrece dos paradas de foco (navegar / vincular) y Enter en cada una hace lo suyo
expected: Dos controles de foco independientes, cada uno activable con Enter.
result: [pending]

### 3. Cerrar el panel de vinculo SIN pulsar confirmar, y reabrirlo
expected: La serie sigue sin vincular (mirar una propuesta no la acepta).
result: [pending]

### 4. Elegir una alternativa distinta de la propuesta, fijar offset y confirmar
expected: El panel se cierra y la serie muestra la entrada ELEGIDA, no la propuesta original.
result: [pending]

### 5. Reabrir el panel de una serie ya vinculada
expected: Sigue vinculada a lo elegido, y no se propone nada nuevo (el vinculo cortocircuita el matcher).
result: [pending]

### 6. Desvincular una serie
expected: La serie vuelve a "sin vincular".
result: [pending]

### 7. Reiniciar la app despues de confirmar un vinculo
expected: El vinculo persiste (esta almacenado, no en memoria).
result: [pending]

### 8. Con DOS series distintas en la MISMA carpeta raiz (biblioteca plana), vincular solo la primera
expected: La segunda serie sigue viendose "sin vincular" (la clave es source_id, no series_id).
result: [pending]

### 9. Terminar de leer un capitulo de una serie SIN vincular
expected: El lector muestra el mensaje "no vinculada, vinculala" en espanol (el reason del backend), no silencio.
result: [pending]

### 10. Con una carpeta de biblioteca PLANA (CBZ colgando de la raiz, series_id/source_id = "0:.")
expected: Esa serie tambien se puede vincular y el vinculo sobrevive (no-regresion Fase 3).
result: [pending]

## Summary

total: 10
passed: 0
issues: 0
pending: 10
skipped: 0
blocked: 0

## Gaps
