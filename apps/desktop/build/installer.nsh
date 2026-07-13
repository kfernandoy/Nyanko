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
;
; PERO customCheckAppRunning NO ES ADITIVA: es la rama !else del check del propio
; electron-builder (app-builder-lib/templates/nsis/include/allowOnlyOneInstallerInstance.nsh:36-42).
; Definirla DESACTIVA _CHECK_APP_RUNNING, que es quien encuentra, avisa y mata Nyanko.exe
; antes de extraer — incluida su rama ${isUpdated} (Sleep 300 -> FIND -> Sleep 1000 -> KILL),
; que existe EXACTAMENTE para sincronizar con un auto-update: quitAndInstall() lanza el
; instalador ANTES de que la app termine de cerrarse. Sin ella, la extracción corre una carrera
; contra un Nyanko.exe todavía vivo que mantiene bloqueado app.asar. En máquina rápida la
; ganamos y parece que funciona; por eso ningún gate por fase lo vio. (B-1, audit v0.2)
;
; Así que la reconstruimos a mano: matamos el sidecar (lo nuestro) Y volvemos a llamar al check
; del framework (lo que la macro había desactivado).
;
; El !include y el Var pid son OBLIGATORIOS y no sobran: allowOnlyOneInstallerInstance.nsh:5
; los mete bajo `!ifmacrondef customCheckAppRunning`, es decir, SOLO si esta macro NO existe.
; Como sí existe, ese include no ocurre y _CHECK_APP_RUNNING se quedaría sin ${GetProcessInfo}
; ni $pid. Nuestro installer.nsh se inyecta en la cabecera del script (NsisTarget.js:600),
; antes de esa guarda, así que los proveemos nosotros.
!include "getProcessInfo.nsh"
Var pid

!macro customCheckAppRunning
  nsExec::Exec 'taskkill /F /IM nyanko-api.exe /T'
  !insertmacro IS_POWERSHELL_AVAILABLE
  !insertmacro _CHECK_APP_RUNNING
!macroend

; ---------------------------------------------------------------------------
; D-02 — RAMA A: migración 0.1.15 (Tauri) → 0.2.0 (Electron).
;
; Desinstalamos la app Tauri en silencio ANTES de instalar. Se puede hacer porque el
; experimento del gate D-02 lo DEMOSTRÓ sobre una instalación 0.1.15 real (2026-07-12):
; el uninstall silencioso de Tauri NO borra %APPDATA%\app.nyanko.desktop — la biblioteca
; del usuario (nyanko.sqlite3, historial, tokens) queda byte a byte idéntica antes y después.
; Ese hecho medido es lo único que autoriza ejecutar este binario. Junto con
; `deleteAppDataOnUninstall: false` en electron-builder.yml, cierra DATA-01: ningún camino
; del instalador toca la biblioteca.
;
; Valores LITERALES medidos en el registro real (NO son suposiciones, no se "corrigen"):
;   Colmena/clave : HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall\Nyanko
;                   (una clave con nombre, NO un GUID entre llaves)
;   UninstallString: "C:\Users\<user>\AppData\Local\Nyanko\uninstall.exe"
;   InstallLocation: "C:\Users\<user>\AppData\Local\Nyanko"
;   Las COMILLAS forman parte del dato del registro → hay que quitarlas o la "ruta"
;   resultante lleva comillas literales y no es una ruta.
;
; POR QUÉ EL `_?=` (no lo quites, no lo "simplifiques" a un ExecWait pelado):
; un uninstaller NSIS se copia a %TEMP% como Au_.exe, relanza esa copia y el proceso
; ORIGINAL retorna al instante (medido: 2,5 s, con borrado aún en curso detrás). Con un
; ExecWait normal seguiríamos adelante creando $SMPROGRAMS\Nyanko.lnk mientras el
; uninstaller rezagado sigue borrando el SUYO — que se llama IGUAL — y se llevaría por
; delante nuestro acceso directo recién creado. `_?=<dir>` obliga al uninstaller a correr
; EN SITIO y de verdad síncrono. Precio obligatorio de `_?=`: con él el uninstaller ya NO
; se autoborra ni borra su directorio, así que rematamos a mano con Delete + RMDir /r.
; Sin ese remate esta rama deja exactamente la basura que dice eliminar.
;
; Nota: el exe de Tauri es nyanko-desktop.exe y el de Electron Nyanko.exe (nombres
; DISTINTOS: instalar encima no pisaría nada). El RMDir /r se lo lleva todo — y el
; $INSTDIR de Electron es otro directorio, así que no se borra a sí mismo.
; ---------------------------------------------------------------------------
!macro NyankoUnquote VAR
  StrCpy $R9 ${VAR} 1
  StrCmp $R9 '"' 0 +3
    StrCpy ${VAR} ${VAR} "" 1
    StrCpy ${VAR} ${VAR} -1
!macroend

!macro customInit
  Push $0
  Push $1
  Push $R9

  ReadRegStr $0 HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Nyanko" "UninstallString"
  ReadRegStr $1 HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Nyanko" "InstallLocation"
  !insertmacro NyankoUnquote $0
  !insertmacro NyankoUnquote $1

  ; Usuario nuevo (sin Tauri): no hay nada que desinstalar. Sin esta guarda un instalador
  ; limpio se comería un ExecWait de una ruta vacía. (T-05-10)
  StrCmp $0 "" nyanko_sin_tauri
  StrCmp $1 "" nyanko_sin_tauri

  ; Síncrono de verdad. Continuamos pase lo que pase: un uninstaller que falle no puede
  ; abortar la instalación de la versión nueva.
  ExecWait '"$0" /S _?=$1'
  Delete "$0"
  RMDir /r "$1"

  nyanko_sin_tauri:
  Pop $R9
  Pop $1
  Pop $0
!macroend
