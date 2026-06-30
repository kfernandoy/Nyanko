import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";

export type Lang = "es" | "en";
export type Theme = "dark" | "light";
export type TitleLanguage = "ROMAJI" | "ENGLISH" | "NATIVE";
export type DiscordFields = { title: boolean; user: boolean; elapsed: boolean };
const DEFAULT_DISCORD_FIELDS: DiscordFields = { title: true, user: true, elapsed: true };

// ponytail: plain dictionary + context, no i18n library for two languages.
// Keys are dot-namespaced by view. Missing key falls back to Spanish, then the key itself.
const translations: Record<Lang, Record<string, string>> = {
  es: {
    "nav.library": "Anime",
    "nav.manga": "Manga",
    "nav.now-playing": "Reproduciendo",
    "nav.history": "Registro",
    "nav.activity": "Actividad",
    "nav.seasons": "Temporadas",
    "nav.statistics": "Estadísticas",
    "nav.discovery": "Descubrir",
    "nav.settings": "Ajustes",

    "settings.tab.providers": "Proveedores",
    "settings.tab.preferences": "Preferencias",
    "settings.tab.system": "Sistema",
    "settings.tab.library": "Biblioteca",
    "settings.tab.app": "Aplicación",
    "settings.tab.recognition": "Reconocimiento",
    "settings.tab.torrents": "Torrents",
    "settings.subtab.anime": "Anime",
    "settings.subtab.general": "General",
    "settings.subtab.players": "Reproductores",
    "settings.subtab.streaming": "Plataformas de Streaming",
    "settings.soon": "próximamente",
    "settings.appearance.title": "Apariencia",
    "settings.appearance.subtitle": "Idioma y tema de la aplicación",
    "settings.appearance.language": "Idioma",
    "settings.appearance.theme": "Tema",
    "settings.theme.dark": "Oscuro",
    "settings.theme.light": "Claro",
    "settings.lang.es": "Español",
    "settings.lang.en": "Inglés",

    "discover.anime": "Anime",
    "discover.manga": "Manga",
    "discover.search.anime": "Buscar anime…",
    "discover.search.manga": "Buscar manga…",
    "discover.sort.popularity": "Más popular",
    "discover.sort.score": "Mejor valorado",
    "discover.format.any": "Cualquier formato",
    "discover.status.any": "Cualquier estado",
    "discover.year": "Año",
    "discover.season.any": "Cualquier temporada",
    "discover.genre.any": "Cualquier género",
    "discover.adult": "Incluir adulto",
    "discover.showWontWatch": "Mostrar \"no lo veré\"",
    "discover.loading": "Buscando…",
    "discover.empty": "No se encontraron resultados",
    "discover.prev": "Anterior",
    "discover.next": "Siguiente",
    "discover.page": "Página",
    "discover.add.watching": "Añadir a Viendo",
    "discover.add.reading": "Añadir a Leyendo",
    "discover.add.planning": "Añadir a Planeados",
    "discover.wontWatch": "No lo veré",
    "discover.wontWatch.remove": "Quitar de \"No lo veré\"",
    "season.winter": "Invierno",
    "season.spring": "Primavera",
    "season.summer": "Verano",
    "season.fall": "Otoño",

    "nav.torrents": "Torrents",
    "torrents.title": "Torrents",
    "torrents.refresh": "Refrescar ahora",
    "torrents.refreshing": "Actualizando…",
    "torrents.empty": "Sin episodios nuevos por ahora.",
    "torrents.download": "Descargar",
    "torrents.discard": "Descartar",
    "torrents.sources": "Fuentes RSS",
    "torrents.filters": "Reglas",
    "torrents.add": "Añadir",
    "torrents.delete": "Eliminar",
    "torrents.autoCheck": "Comprobar en segundo plano",
    "torrents.interval": "Intervalo (min)",
    "torrents.downloadMode": "Modo de descarga",
    "torrents.watchFolder": "Carpeta vigilada",
    "torrents.preferredResolution": "Resolución preferida",
    "torrents.notify": "Hay episodios nuevos disponibles",

    "view.library.eyebrow": "TU BIBLIOTECA", "view.library.title": "Continúa donde quedaste.",
    "view.manga.eyebrow": "TU MANGA", "view.manga.title": "Lecturas en curso.",
    "view.now-playing.eyebrow": "REPRODUCIENDO", "view.now-playing.title": "Detectado en este momento.",
    "view.history.eyebrow": "HISTORIAL LOCAL", "view.history.title": "Decisiones y progreso detectado.",
    "view.activity.eyebrow": "ACTIVIDAD RECIENTE", "view.activity.title": "Tu actividad reciente.",
    "view.seasons.eyebrow": "TEMPORADA", "view.seasons.title": "Anime de la temporada.",
    "view.statistics.eyebrow": "ESTADÍSTICAS", "view.statistics.title": "Tu tiempo entre historias.",
    "view.discovery.eyebrow": "DESCUBRIMIENTO", "view.discovery.title": "Busca y filtra anime.",
    "view.torrents.eyebrow": "TORRENTS", "view.torrents.title": "Episodios disponibles.",
    "view.settings.eyebrow": "AJUSTES", "view.settings.title": "Controla cómo detecta Nyanko.",

    "account.pauseDetection": "Pausar detección", "account.resumeDetection": "Reanudar detección",
    "account.settings": "Ajustes", "account.logout": "Cerrar sesión",

    "common.back": "Volver", "common.error.generic": "No se pudo completar la operación.",
    "common.connectAccount": "Conecta tu cuenta", "common.connectAccount.detail": "Tu información aparecerá aquí.",
    "common.loadingInfo": "Cargando información…", "common.loading": "Cargando…",
    "common.noResults": "No hay resultados", "common.tryOtherFilter": "Prueba otro filtro o búsqueda.",
    "common.reload": "Recargar", "common.unknown": "Desconocido", "common.anime": "Anime",

    "filter.watching": "Viendo", "filter.reading": "Leyendo", "filter.planning": "Planeados",
    "filter.completed": "Completados", "filter.paused": "Pausados", "filter.dropped": "Abandonados", "filter.all": "Todos",
    "badge.CURRENT": "Viendo", "badge.COMPLETED": "Completado", "badge.PAUSED": "Pausado",
    "badge.DROPPED": "Abandonado", "badge.PLANNING": "Planeado",

    "lib.sort.title": "Título A–Z", "lib.sort.progress": "Progreso descendente",
    "lib.sort.score": "Puntuación descendente", "lib.sort.updated": "Última actualización",
    "lib.format.all": "Todos los formatos", "lib.year.all": "Todos los años",
    "lib.genre.all": "Todos los géneros", "lib.tag.all": "Todas las etiquetas",
    "lib.layout.grid": "Cuadrícula", "lib.layout.list": "Lista",
    "lib.search.anime": "Buscar anime…", "lib.search.manga": "Buscar manga…",
    "lib.loading.anime": "Cargando biblioteca…", "lib.loading.manga": "Cargando manga…",
    "lib.row.completed": "Completado", "lib.row.addEpisode": "+1 episodio", "lib.row.edit": "Editar",

    "stats.tab.anime": "Anime", "stats.tab.manga": "Manga",
    "stats.none": "No hay estadísticas disponibles",
    "stats.empty.anime": "Aún no hay anime en tus estadísticas", "stats.empty.manga": "Aún no hay manga en tus estadísticas",
    "stats.hero.animeCount": "Anime en tu lista", "stats.hero.mangaCount": "Manga en tu lista",
    "stats.hero.episodes": "Episodios vistos", "stats.hero.chapters": "Capítulos leídos",
    "stats.completedPct": "completados", "stats.perTitle": "por título",
    "stats.watchTime": "Tiempo viendo", "stats.days": "días", "stats.inProgress": "En curso",
    "stats.planned": "planeados", "stats.meanScore": "Puntuación media",
    "stats.outOf100": "sobre 100", "stats.unscored": "sin puntuar",
    "stats.completed": "Completados", "stats.paused": "Pausados", "stats.dropped": "Abandonados",
    "stats.genres": "Géneros principales", "stats.formats": "Formatos", "stats.years": "Años",
    "stats.studios": "Estudios", "stats.countries": "Países", "stats.export": "Exportar JSON",

    "np.none": "No hay reproducción detectada", "np.none.detail": "Abre un reproductor compatible y vuelve aquí.",
    "np.local.title": "Pendientes en local", "np.local.episode": "Episodio", "np.local.available": "disponibles", "np.local.play": "Reproducir episodio", "np.playerSource": "Reproductor", "np.movie": "Película",
    "local.seeMore": "Ver más", "local.back": "Volver", "local.title": "Biblioteca local", "local.loading": "Cargando…", "local.empty": "No hay series escaneadas.", "local.episodes": "episodios", "local.unmatched": "sin asociar",
    "np.source": "FUENTE", "np.confidence": "CONFIANZA", "np.paused": "PAUSADO", "np.finished": "FINALIZADO",
    "np.episode": "Episodio", "np.episode.unknown": "Episodio sin identificar", "np.activeWindow": "ventana activa",
    "np.correct.title": "Corregir coincidencia",
    "np.correct.desc": "La búsqueda se hace en tu biblioteca y en tu proveedor activo a la vez. Si la serie ya está en tu lista, aparece con su estado.",
    "np.correct.placeholder": "Escribe al menos 2 caracteres…",
    "np.viewEntry": "Ver ficha",
    "np.search": "Buscar", "np.searching": "Buscando…", "np.useThis": "Usar este",
    "np.addWatching": "Añadir a Viendo", "np.addPlanning": "A Planeados",
    "np.notFoundPre": "No se encontró \"", "np.notFoundPost": "\" en tu biblioteca ni en tu proveedor activo.",
    "np.cancel": "Cancelar", "np.suggestedMatch": "Coincidencia sugerida",
    "np.confirm": "Confirmar episodio", "np.tracked": "Actualizado",
    "np.autoSaving": "Se guardará automáticamente",
    "np.completed": "Serie completada", "np.startRewatch": "Reviendo", "np.rewatching": "Reviendo",
    "np.savingIn": "Se guardará en", "np.saving": "Guardando…",
    "np.manuallyCorrected": "corregida manualmente", "np.correct": "Corregir",
    "np.ignore": "Ignorar", "np.undoLast": "Deshacer última", "np.episodes": "episodios",
    "np.noMatch": "Sin coincidencia en tu biblioteca", "np.noMatch.desc": "No se encontró un anime que coincida con este título.",
    "np.otherOptions": "¿Era otra serie?",

    "seasons.search": "Buscar en la temporada…", "seasons.empty": "No hay títulos para estos filtros",
    "seasons.sort.popularity": "Popularidad", "seasons.sort.title": "Título A–Z",
    "seasons.sort.date": "Fecha de inicio", "seasons.sort.score": "Puntuación",
    "seasons.group.tv": "TV", "seasons.group.tvshort": "TV Short",
    "seasons.group.special": "ONA / OVA / Especial", "seasons.group.movies": "Películas", "seasons.group.other": "Otros",
    "seasons.fmt.special": "Especial", "seasons.fmt.movie": "Película",
    "seasons.studioUnknown": "Estudio desconocido", "seasons.episodes": "episodios",
    "seasons.noScore": "Sin puntuación", "seasons.epIn": "en", "seasons.tba": "Fecha por anunciar",

    "activity.type.all": "Todos los tipos", "activity.type.progress": "Avances de episodio",
    "activity.type.status": "Cambios de estado", "activity.status.all": "Todos los estados",
    "activity.from": "Actividad desde", "activity.none": "No hay actividad reciente",
    "activity.loadMore": "Cargar más", "activity.ep": "ep",

    "detail.tab.info": "Información", "detail.tab.cast": "Reparto", "detail.tab.recommendations": "Recomendaciones",
    "detail.tab.editList": "Editar lista", "detail.tab.addList": "Añadir a lista",
    "detail.synopsis": "Sinopsis", "detail.altTitles": "Títulos alternativos",
    "detail.trailer": "Ver trailer en YouTube ↗", "detail.related": "Obras relacionadas",
    "detail.characters": "Personajes", "detail.staff": "Staff",
    "detail.main": "Principal", "detail.secondary": "Secundario", "detail.openIn": "Abrir en",
    "detail.changeSaved": "Cambio guardado.", "detail.undo": "↩ Deshacer",
    "detail.result.saved": "Guardado", "detail.result.failed": "Falló",
    "detail.fact.status": "Estado", "detail.fact.source": "Origen", "detail.fact.chapters": "Capítulos",
    "detail.fact.volumes": "Volúmenes", "detail.fact.episodes": "Episodios", "detail.fact.duration": "Duración",
    "detail.fact.studios": "Estudios", "detail.fact.country": "País", "detail.fact.nextEp": "Próximo episodio",
    "detail.fact.score": "Puntuación",
    "detail.edit.status": "Estado", "detail.edit.progress": "Progreso", "detail.edit.score": "Puntuación",
    "detail.edit.repeat": "Repeticiones", "detail.edit.startDate": "Fecha de inicio", "detail.edit.endDate": "Fecha de término",
    "detail.edit.notes": "Notas", "detail.edit.private": "Entrada privada", "detail.edit.saving": "Guardando…",
    "detail.edit.saveChanges": "Guardar cambios", "detail.edit.addToList": "Añadir a la lista", "detail.edit.delete": "Eliminar",
    "detail.close": "Cerrar",
    "tags.title": "Etiquetas", "tags.add": "Añadir", "tags.placeholder": "Añadir etiqueta…",
  },
  en: {
    "nav.library": "Anime",
    "nav.manga": "Manga",
    "nav.now-playing": "Now Playing",
    "nav.history": "History",
    "nav.activity": "Activity",
    "nav.seasons": "Seasons",
    "nav.statistics": "Statistics",
    "nav.discovery": "Discover",
    "nav.settings": "Settings",

    "settings.tab.providers": "Providers",
    "settings.tab.preferences": "Preferences",
    "settings.tab.system": "System",
    "settings.tab.library": "Library",
    "settings.tab.app": "Application",
    "settings.tab.recognition": "Recognition",
    "settings.tab.torrents": "Torrents",
    "settings.subtab.anime": "Anime",
    "settings.subtab.general": "General",
    "settings.subtab.players": "Players",
    "settings.subtab.streaming": "Streaming Platforms",
    "settings.soon": "coming soon",
    "settings.appearance.title": "Appearance",
    "settings.appearance.subtitle": "Application language and theme",
    "settings.appearance.language": "Language",
    "settings.appearance.theme": "Theme",
    "settings.theme.dark": "Dark",
    "settings.theme.light": "Light",
    "settings.lang.es": "Spanish",
    "settings.lang.en": "English",

    "discover.anime": "Anime",
    "discover.manga": "Manga",
    "discover.search.anime": "Search anime…",
    "discover.search.manga": "Search manga…",
    "discover.sort.popularity": "Most popular",
    "discover.sort.score": "Top rated",
    "discover.format.any": "Any format",
    "discover.status.any": "Any status",
    "discover.year": "Year",
    "discover.season.any": "Any season",
    "discover.genre.any": "Any genre",
    "discover.adult": "Include adult",
    "discover.showWontWatch": "Show \"won't watch\"",
    "discover.loading": "Searching…",
    "discover.empty": "No results found",
    "discover.prev": "Previous",
    "discover.next": "Next",
    "discover.page": "Page",
    "discover.add.watching": "Add to Watching",
    "discover.add.reading": "Add to Reading",
    "discover.add.planning": "Add to Planning",
    "discover.wontWatch": "Won't watch",
    "discover.wontWatch.remove": "Remove from \"Won't watch\"",
    "season.winter": "Winter",
    "season.spring": "Spring",
    "season.summer": "Summer",
    "season.fall": "Fall",

    "nav.torrents": "Torrents",
    "torrents.title": "Torrents",
    "torrents.refresh": "Refresh now",
    "torrents.refreshing": "Refreshing…",
    "torrents.empty": "No new episodes right now.",
    "torrents.download": "Download",
    "torrents.discard": "Dismiss",
    "torrents.sources": "RSS Sources",
    "torrents.filters": "Rules",
    "torrents.add": "Add",
    "torrents.delete": "Delete",
    "torrents.autoCheck": "Check in background",
    "torrents.interval": "Interval (min)",
    "torrents.downloadMode": "Download mode",
    "torrents.watchFolder": "Watch folder",
    "torrents.preferredResolution": "Preferred resolution",
    "torrents.notify": "New episodes available",

    "view.library.eyebrow": "YOUR LIBRARY", "view.library.title": "Pick up where you left off.",
    "view.manga.eyebrow": "YOUR MANGA", "view.manga.title": "Currently reading.",
    "view.now-playing.eyebrow": "NOW PLAYING", "view.now-playing.title": "Detected right now.",
    "view.history.eyebrow": "LOCAL HISTORY", "view.history.title": "Decisions and detected progress.",
    "view.activity.eyebrow": "RECENT ACTIVITY", "view.activity.title": "Your recent activity.",
    "view.seasons.eyebrow": "SEASON", "view.seasons.title": "Anime of the season.",
    "view.statistics.eyebrow": "STATISTICS", "view.statistics.title": "Your time between stories.",
    "view.discovery.eyebrow": "DISCOVERY", "view.discovery.title": "Search and filter anime.",
    "view.torrents.eyebrow": "TORRENTS", "view.torrents.title": "Available episodes.",
    "view.settings.eyebrow": "SETTINGS", "view.settings.title": "Control how Nyanko detects.",

    "account.pauseDetection": "Pause detection", "account.resumeDetection": "Resume detection",
    "account.settings": "Settings", "account.logout": "Log out",

    "common.back": "Back", "common.error.generic": "The operation could not be completed.",
    "common.connectAccount": "Connect your account", "common.connectAccount.detail": "Your information will appear here.",
    "common.loadingInfo": "Loading details…", "common.loading": "Loading…",
    "common.noResults": "No results", "common.tryOtherFilter": "Try another filter or search.",
    "common.reload": "Reload", "common.unknown": "Unknown", "common.anime": "Anime",

    "filter.watching": "Watching", "filter.reading": "Reading", "filter.planning": "Planned",
    "filter.completed": "Completed", "filter.paused": "Paused", "filter.dropped": "Dropped", "filter.all": "All",
    "badge.CURRENT": "Watching", "badge.COMPLETED": "Completed", "badge.PAUSED": "Paused",
    "badge.DROPPED": "Dropped", "badge.PLANNING": "Planned",

    "lib.sort.title": "Title A–Z", "lib.sort.progress": "Progress descending",
    "lib.sort.score": "Score descending", "lib.sort.updated": "Last updated",
    "lib.format.all": "All formats", "lib.year.all": "All years",
    "lib.genre.all": "All genres", "lib.tag.all": "All tags",
    "lib.layout.grid": "Grid", "lib.layout.list": "List",
    "lib.search.anime": "Search anime…", "lib.search.manga": "Search manga…",
    "lib.loading.anime": "Loading library…", "lib.loading.manga": "Loading manga…",
    "lib.row.completed": "Completed", "lib.row.addEpisode": "+1 episode", "lib.row.edit": "Edit",

    "stats.tab.anime": "Anime", "stats.tab.manga": "Manga",
    "stats.none": "No statistics available",
    "stats.empty.anime": "No anime in your statistics yet", "stats.empty.manga": "No manga in your statistics yet",
    "stats.hero.animeCount": "Anime in your list", "stats.hero.mangaCount": "Manga in your list",
    "stats.hero.episodes": "Episodes watched", "stats.hero.chapters": "Chapters read",
    "stats.completedPct": "completed", "stats.perTitle": "per title",
    "stats.watchTime": "Watch time", "stats.days": "days", "stats.inProgress": "In progress",
    "stats.planned": "planned", "stats.meanScore": "Mean score",
    "stats.outOf100": "out of 100", "stats.unscored": "unscored",
    "stats.completed": "Completed", "stats.paused": "Paused", "stats.dropped": "Dropped",
    "stats.genres": "Top genres", "stats.formats": "Formats", "stats.years": "Years",
    "stats.studios": "Studios", "stats.countries": "Countries", "stats.export": "Export JSON",

    "np.none": "No playback detected", "np.none.detail": "Open a compatible player and come back here.",
    "np.local.title": "Available locally", "np.local.episode": "Episode", "np.local.available": "available", "np.local.play": "Play episode", "np.playerSource": "Player", "np.movie": "Movie",
    "local.seeMore": "See more", "local.back": "Back", "local.title": "Local library", "local.loading": "Loading…", "local.empty": "No scanned series.", "local.episodes": "episodes", "local.unmatched": "unmatched",
    "np.source": "SOURCE", "np.confidence": "CONFIDENCE", "np.paused": "PAUSED", "np.finished": "FINISHED",
    "np.episode": "Episode", "np.episode.unknown": "Unidentified episode", "np.activeWindow": "active window",
    "np.correct.title": "Correct match",
    "np.correct.desc": "The search runs in your library and your active provider at once. If the show is already on your list, it appears with its status.",
    "np.correct.placeholder": "Type at least 2 characters…",
    "np.viewEntry": "View entry",
    "np.search": "Search", "np.searching": "Searching…", "np.useThis": "Use this",
    "np.addWatching": "Add to Watching", "np.addPlanning": "To Planned",
    "np.notFoundPre": "\"", "np.notFoundPost": "\" was not found in your library or your active provider.",
    "np.cancel": "Cancel", "np.suggestedMatch": "Suggested match",
    "np.confirm": "Confirm episode", "np.tracked": "Updated",
    "np.autoSaving": "Saves automatically",
    "np.completed": "Series completed", "np.startRewatch": "Rewatch", "np.rewatching": "Rewatching",
    "np.savingIn": "Saving in", "np.saving": "Saving…",
    "np.manuallyCorrected": "manually corrected", "np.correct": "Correct",
    "np.ignore": "Ignore", "np.undoLast": "Undo last", "np.episodes": "episodes",
    "np.noMatch": "No match in your library", "np.noMatch.desc": "No anime matching this title was found.",
    "np.otherOptions": "Was it another series?",

    "seasons.search": "Search the season…", "seasons.empty": "No titles for these filters",
    "seasons.sort.popularity": "Popularity", "seasons.sort.title": "Title A–Z",
    "seasons.sort.date": "Start date", "seasons.sort.score": "Score",
    "seasons.group.tv": "TV", "seasons.group.tvshort": "TV Short",
    "seasons.group.special": "ONA / OVA / Special", "seasons.group.movies": "Movies", "seasons.group.other": "Others",
    "seasons.fmt.special": "Special", "seasons.fmt.movie": "Movie",
    "seasons.studioUnknown": "Unknown studio", "seasons.episodes": "episodes",
    "seasons.noScore": "No score", "seasons.epIn": "in", "seasons.tba": "Date to be announced",

    "activity.type.all": "All types", "activity.type.progress": "Episode progress",
    "activity.type.status": "Status changes", "activity.status.all": "All statuses",
    "activity.from": "Activity since", "activity.none": "No recent activity",
    "activity.loadMore": "Load more", "activity.ep": "ep",

    "detail.tab.info": "Information", "detail.tab.cast": "Cast", "detail.tab.recommendations": "Recommendations",
    "detail.tab.editList": "Edit list", "detail.tab.addList": "Add to list",
    "detail.synopsis": "Synopsis", "detail.altTitles": "Alternative titles",
    "detail.trailer": "Watch trailer on YouTube ↗", "detail.related": "Related works",
    "detail.characters": "Characters", "detail.staff": "Staff",
    "detail.main": "Main", "detail.secondary": "Supporting", "detail.openIn": "Open in",
    "detail.changeSaved": "Change saved.", "detail.undo": "↩ Undo",
    "detail.result.saved": "Saved", "detail.result.failed": "Failed",
    "detail.fact.status": "Status", "detail.fact.source": "Source", "detail.fact.chapters": "Chapters",
    "detail.fact.volumes": "Volumes", "detail.fact.episodes": "Episodes", "detail.fact.duration": "Duration",
    "detail.fact.studios": "Studios", "detail.fact.country": "Country", "detail.fact.nextEp": "Next episode",
    "detail.fact.score": "Score",
    "detail.edit.status": "Status", "detail.edit.progress": "Progress", "detail.edit.score": "Score",
    "detail.edit.repeat": "Rewatches", "detail.edit.startDate": "Start date", "detail.edit.endDate": "End date",
    "detail.edit.notes": "Notes", "detail.edit.private": "Private entry", "detail.edit.saving": "Saving…",
    "detail.edit.saveChanges": "Save changes", "detail.edit.addToList": "Add to list", "detail.edit.delete": "Delete",
    "detail.close": "Close",
    "tags.title": "Tags", "tags.add": "Add", "tags.placeholder": "Add tag…",
  },
};

type AppContextValue = {
  lang: Lang;
  setLang: (lang: Lang) => void;
  t: (key: string) => string;
  theme: Theme;
  setTheme: (theme: Theme) => void;
  titleLanguage: TitleLanguage;
  setTitleLanguage: (language: TitleLanguage) => void;
  discordRpc: boolean;
  setDiscordRpc: (enabled: boolean) => void;
  discordFields: DiscordFields;
  setDiscordFields: (fields: DiscordFields) => void;
};

const AppContext = createContext<AppContextValue | null>(null);

export function AppSettingsProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(() => (localStorage.getItem("lang") as Lang) || "es");
  const [theme, setThemeState] = useState<Theme>(() => (localStorage.getItem("theme") as Theme) || "dark");
  const [titleLanguage, setTitleLanguageState] = useState<TitleLanguage>(() => (localStorage.getItem("titleLanguage") as TitleLanguage) || "ROMAJI");
  const [discordRpc, setDiscordRpcState] = useState<boolean>(() => localStorage.getItem("discordRpc") === "1");
  const [discordFields, setDiscordFieldsState] = useState<DiscordFields>(() => {
    try { return { ...DEFAULT_DISCORD_FIELDS, ...JSON.parse(localStorage.getItem("discordFields") || "{}") }; }
    catch { return DEFAULT_DISCORD_FIELDS; }
  });

  useEffect(() => { document.documentElement.dataset.theme = theme; }, [theme]);

  const setLang = useCallback((next: Lang) => { setLangState(next); localStorage.setItem("lang", next); }, []);
  const setTheme = useCallback((next: Theme) => { setThemeState(next); localStorage.setItem("theme", next); }, []);
  const setTitleLanguage = useCallback((next: TitleLanguage) => { setTitleLanguageState(next); localStorage.setItem("titleLanguage", next); }, []);
  const setDiscordRpc = useCallback((next: boolean) => { setDiscordRpcState(next); localStorage.setItem("discordRpc", next ? "1" : "0"); }, []);
  const setDiscordFields = useCallback((next: DiscordFields) => { setDiscordFieldsState(next); localStorage.setItem("discordFields", JSON.stringify(next)); }, []);
  const t = useCallback((key: string) => translations[lang][key] ?? translations.es[key] ?? key, [lang]);

  return <AppContext.Provider value={{ lang, setLang, t, theme, setTheme, titleLanguage, setTitleLanguage, discordRpc, setDiscordRpc, discordFields, setDiscordFields }}>{children}</AppContext.Provider>;
}

export function useApp(): AppContextValue {
  const value = useContext(AppContext);
  if (!value) throw new Error("useApp must be used within AppSettingsProvider");
  return value;
}
