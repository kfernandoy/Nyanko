; El sidecar nyanko-api.exe sobrevive al updater (es un proceso aparte que Tauri/NSIS
; no cierra) y mantiene bloqueados _internal\* y el propio exe → el copiado del
; instalador fallaba y había que matar el proceso a mano. Lo cerramos antes de instalar.
!macro NSIS_HOOK_PREINSTALL
  nsExec::Exec 'taskkill /F /IM nyanko-api.exe /T'
!macroend
