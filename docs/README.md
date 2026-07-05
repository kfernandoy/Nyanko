# Nyanko

Idiomas: [Espanol](#espanol) | [English](#english)

## Espanol

Nyanko es una aplicacion de escritorio para llevar tu lista de anime y manga,
detectar lo que estas viendo y actualizar el progreso sin depender de una web
abierta todo el tiempo.

### Que hace

- Conecta cuentas de AniList, MyAnimeList y Kitsu.
- Muestra tu biblioteca de anime y manga con filtros, busqueda, estados,
  progreso, puntuacion y detalle de cada obra.
- Permite editar entradas: estado, progreso, puntuacion, fechas, notas,
  privacidad, repeticiones y eliminacion de la lista.
- Detecta reproduccion local desde reproductores como mpv, VLC, MPC-HC,
  PotPlayer, SMTC, procesos con archivos abiertos y la ventana activa como
  respaldo.
- Detecta reproduccion en navegador mediante una extension para Chromium y
  Firefox.
- Sugiere coincidencias cuando reconoce una serie, deja corregirlas y recuerda
  las correcciones.
- Puede confirmar progreso automaticamente cuando la coincidencia y el avance
  cumplen la configuracion del usuario.
- Guarda historial local de detecciones, confirmaciones, errores, ignorados y
  deshacer.
- Escanea carpetas locales para encontrar episodios disponibles y reproducir el
  siguiente episodio desde la app.
- Consulta torrents por RSS, agrupa resultados por serie y permite abrir magnet
  o guardar archivos `.torrent`.

### Como funciona

Nyanko corre como una app de escritorio con un servicio local privado. La interfaz
habla con ese servicio en `127.0.0.1`; no abre una API publica en la red.

Al conectar un proveedor, Nyanko importa la biblioteca y guarda una copia local
normalizada. Esa copia permite buscar, mostrar detalles, cachear datos y seguir
usando informacion reciente cuando un proveedor responde lento o esta caido.

Cuando detecta un episodio, Nyanko normaliza el titulo, busca la mejor coincidencia
en la biblioteca o en el catalogo del proveedor activo, y muestra el resultado en
Reproduciendo. Si la confianza es suficiente y la automatizacion esta activada,
actualiza el progreso; si no, pide confirmacion.

Las ediciones se aplican primero en local y luego se envian al proveedor. Si algo
falla, quedan registradas para reintento o resolucion manual.

### Proveedores

- **AniList**: anime, manga, actividad, temporadas, estadisticas, busqueda,
  detalle y edicion.
- **MyAnimeList**: anime, manga, busqueda, detalle, estadisticas derivadas de la
  biblioteca y edicion de entradas. Sus preferencias de perfil son de solo lectura
  desde la API.
- **Kitsu**: anime, busqueda, descubrimiento, detalle, edicion y preferencias.
  No expone manga, actividad ni temporadas en Nyanko.

Cada proveedor mantiene sus propios IDs y datos remotos. Nyanko usa un modelo local
para relacionar obras cuando hay una coincidencia confiable, sin mezclar IDs entre
servicios.

### Extension del navegador

La extension observa metadatos de la pagina y el estado del elemento `<video>`.
No envia el video ni el contenido reproducido.

La extension se empareja automaticamente con la app cuando Nyanko esta abierto.
El usuario activa los sitios desde las opciones de la extension; por defecto no
rastrea sitios hasta que se habilitan adaptadores.

### Ajustes principales

- Proveedor principal y cuenta conectada por proveedor.
- Idioma de interfaz, tema y preferencia de idioma de titulos.
- Formato de puntuacion y contenido adulto cuando el proveedor lo permite.
- Deteccion automatica, umbral de confianza y momento de confirmacion.
- Reproductores habilitados.
- Carpetas locales, escaneo al iniciar y vigilancia de cambios.
- Torrents, fuentes RSS, filtros y carpeta de descarga.
- Inicio con Windows, bandeja del sistema y Discord Rich Presence.

### Privacidad y datos locales

Los tokens se guardan en el almacen seguro del sistema operativo. La base local
guarda cache, historial, configuracion, biblioteca normalizada y relaciones entre
proveedores.

Desde Ajustes se pueden sincronizar datos, limpiar cache/historial y desconectar
cuentas.

## English

Nyanko is a desktop app for managing your anime and manga list, detecting what
you are watching, and updating progress without keeping a tracking website open.

### What It Does

- Connects AniList, MyAnimeList, and Kitsu accounts.
- Shows your anime and manga library with filters, search, statuses, progress,
  scores, and details for each title.
- Lets you edit entries: status, progress, score, dates, notes, privacy,
  rewatches, and removal from the list.
- Detects local playback from players such as mpv, VLC, MPC-HC, PotPlayer,
  SMTC, processes with open media files, and the active window as a fallback.
- Detects browser playback through an extension for Chromium and Firefox.
- Suggests matches when it recognizes a series, lets you correct them, and
  remembers corrections.
- Can confirm progress automatically when the match and playback progress meet
  your settings.
- Keeps a local history of detections, confirmations, errors, ignored events,
  and undo actions.
- Scans local folders to find available episodes and play the next episode from
  the app.
- Reads torrent RSS feeds, groups results by series, and lets you open magnet
  links or save `.torrent` files.

### How It Works

Nyanko runs as a desktop app with a private local service. The interface talks to
that service on `127.0.0.1`; it does not expose a public network API.

When you connect a provider, Nyanko imports your library and stores a normalized
local copy. That copy makes search, details, caching, and recent information
available even when a provider is slow or temporarily unavailable.

When Nyanko detects an episode, it normalizes the title, searches for the best
match in your library or in the active provider catalog, and shows the result in
Now Playing. If confidence is high enough and automation is enabled, it updates
progress; otherwise, it asks for confirmation.

Edits are applied locally first and then sent to the provider. If something
fails, it is kept in history for retry or manual resolution.

### Providers

- **AniList**: anime, manga, activity, seasons, statistics, search, details, and
  editing.
- **MyAnimeList**: anime, manga, search, details, statistics derived from the
  library, and entry editing. Profile preferences are read-only through the API.
- **Kitsu**: anime, search, discovery, details, editing, and preferences. Manga,
  activity, and seasons are not exposed in Nyanko.

Each provider keeps its own IDs and remote data. Nyanko uses a local model to
relate titles when there is a reliable match, without mixing IDs between
services.

### Browser Extension

The extension observes page metadata and the state of the `<video>` element. It
does not send the video or watched content.

The extension pairs automatically with the app while Nyanko is open. Sites are
enabled from the extension options; by default, it does not track sites until
adapters are enabled.

### Main Settings

- Primary provider and one connected account per provider.
- Interface language, theme, and title language preference.
- Score format and adult content when the provider supports it.
- Automatic detection, confidence threshold, and confirmation timing.
- Enabled players.
- Local folders, startup scan, and folder watching.
- Torrents, RSS sources, filters, and download folder.
- Start with Windows, system tray, and Discord Rich Presence.

### Privacy And Local Data

Tokens are stored in the operating system secure store. The local database stores
cache, history, configuration, normalized library data, and provider relations.

From Settings, you can sync data, clear cache/history, and disconnect accounts.
