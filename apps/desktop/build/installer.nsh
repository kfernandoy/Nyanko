; El sidecar nyanko-api.exe sobrevive al updater (es un proceso aparte que Electron/NSIS
; no cierra) y mantiene bloqueados _internal\* y el propio exe → el copiado del
; instalador fallaba y había que matar el proceso a mano. Lo cerramos antes de instalar. (D-05)
;
; La macro es customCheckAppRunning y NO customInit — la diferencia es de fondo, no de nombre.
; customInit se inyecta en el .onInit del instalador, es decir ANTES del asistente: en el camino
; asistido (primera instalación, y la migración D-01) median 30-60 s de clicks del usuario
; —selector de idioma + página del EULA— entre el taskkill y la copia de ficheros. En esa ventana
; el usuario puede relanzar Nyanko y respawnear nyanko-api.exe, que vuelve a bloquear _internal\*
; y hace fallar el copiado: exactamente el fallo que D-05 previene. customCheckAppRunning corre
; justo antes de la extracción — es el análogo real del NSIS_HOOK_PREINSTALL de Tauri. (T-05-05)
; No "normalizar" esto a customInit: reabre la ventana.
!macro customCheckAppRunning
  nsExec::Exec 'taskkill /F /IM nyanko-api.exe /T'
!macroend
