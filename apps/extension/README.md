# Extensión de navegador de Nyanko

WebExtension compartida para Chromium y Firefox. Observa únicamente metadatos de la
página y el estado del elemento `<video>`; no almacena ni transmite el contenido
reproducido.

## Compilar

```powershell
npm run build:extension
```

Se generan `dist/chromium` y `dist/firefox`. Carga la carpeta correspondiente como
extensión temporal/sin empaquetar desde la página de extensiones del navegador.

## Emparejar

1. Abre Ajustes en Nyanko y pulsa **Generar código**.
2. Abre las opciones de la extensión.
3. Copia la dirección local y el código mostrados por Nyanko.
4. Define opcionalmente sitios permitidos y bloqueados.

El código dura diez minutos y sólo puede usarse una vez. El token resultante dura 30
días, se renueva automáticamente antes de vencer y puede revocarse desde Nyanko.

El badge y una etiqueta superpuesta indican cuándo una página está siendo observada.
Los eventos pausados limpian la reproducción activa y la extensión vuelve a conectar
automáticamente cuando Nyanko reaparece.

El registro incluye un adaptador genérico basado en JSON-LD/metadatos y un adaptador
inicial de Crunchyroll. Los eventos se clasifican para excluir trailers, previews,
openings y endings del progreso automático.
