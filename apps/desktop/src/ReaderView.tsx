import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type MouseEvent as ReactMouseEvent,
  type WheelEvent as ReactWheelEvent,
} from "react";
import { api } from "./api";
import { useApp } from "./i18n";
import { decodeWindow, pagePairs } from "./readerWindow";
import type { MangaChapter, MangaPage, ReaderMode, ReaderPrefs } from "./types";

const SOURCE_NAME = "local_archive";
const PROGRESS_DEBOUNCE_MS = 500;
const MIN_ZOOM = 1;
const MAX_ZOOM = 4;
const ZOOM_STEP = 0.25;

type Arrastre = {
  x: number;
  y: number;
  origenX: number;
  origenY: number;
};

type Transicion = {
  direccion: "previous" | "next";
  destino: MangaChapter | null;
};

// Las paginas fuera de decodeWindow NO se montan. Tampoco se guardan bitmaps en JS:
// una referencia sobreviviria al <img> y es exactamente el leak que mide RD-09.
export function ReaderView({
  chapter,
  onClose,
  onChapterChange,
}: {
  chapter: MangaChapter;
  onClose: () => void;
  onChapterChange: (next: MangaChapter) => void;
}) {
  const { t } = useApp();
  const [paginas, setPaginas] = useState<MangaPage[]>([]);
  const [capitulos, setCapitulos] = useState<MangaChapter[]>([]);
  const [preferencias, setPreferencias] = useState<ReaderPrefs | null>(null);
  const [paginaActual, setPaginaActual] = useState(1);
  const [cargando, setCargando] = useState(true);
  const [listo, setListo] = useState(false);
  const [errorCarga, setErrorCarga] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const [controlesVisibles, setControlesVisibles] = useState(true);
  const [zoom, setZoom] = useState(MIN_ZOOM);
  const [paneo, setPaneo] = useState({ x: 0, y: 0 });
  const [transicion, setTransicion] = useState<Transicion | null>(null);
  const contenedorVertical = useRef<HTMLDivElement | null>(null);
  const arrastre = useRef<Arrastre | null>(null);
  const huboArrastre = useRef(false);
  const ruedaBloqueada = useRef(false);
  const restaurandoScroll = useRef(false);
  const scrollInicialHecho = useRef(false);
  const modoAnterior = useRef<ReaderMode | null>(null);
  const eventosEmitidos = useRef(new Set<string>());

  useEffect(() => {
    let activo = true;
    setCargando(true);
    setListo(false);
    setErrorCarga(null);
    setAviso(null);
    setZoom(MIN_ZOOM);
    setPaneo({ x: 0, y: 0 });
    setTransicion(null);
    scrollInicialHecho.current = false;
    modoAnterior.current = null;

    Promise.all([
      api.mangaPages(SOURCE_NAME, chapter.source_id),
      api.readerPrefs(SOURCE_NAME, chapter.series_id),
      api.readerProgress(SOURCE_NAME, chapter.source_id),
    ])
      .then(async ([paginasGuardadas, preferenciasGuardadas, progresoGuardado]) => {
        // Si la serie aun no tiene fila, un PUT vacio deja que SQLite aplique el RTL
        // del esquema. El defecto no se duplica en el cliente.
        const preferenciasEfectivas = preferenciasGuardadas
          ?? await api.setReaderPrefs(SOURCE_NAME, chapter.series_id, {});
        if (!activo) return;
        const total = paginasGuardadas.length;
        const paginaGuardada = progresoGuardado?.page ?? 1;
        setPaginas(paginasGuardadas);
        setPreferencias(preferenciasEfectivas);
        setPaginaActual(total > 0 ? Math.min(total, Math.max(1, paginaGuardada)) : 1);
        setListo(true);
      })
      .catch((reason: unknown) => {
        if (activo) setErrorCarga(reason instanceof Error ? reason.message : String(reason));
      })
      .finally(() => {
        if (activo) setCargando(false);
      });

    return () => { activo = false; };
  }, [chapter.series_id, chapter.source_id]);

  useEffect(() => {
    let activo = true;
    void api.mangaChapters(SOURCE_NAME, chapter.series_id)
      .then((hermanos) => {
        if (activo) setCapitulos(hermanos.filter((hermano) => hermano.is_chapter));
      })
      .catch((reason: unknown) => {
        if (activo) setAviso(reason instanceof Error ? reason.message : String(reason));
      });
    return () => { activo = false; };
  }, [chapter.series_id]);

  const total = paginas.length;
  const modo = preferencias?.mode;
  const doblePagina = Boolean(preferencias?.double_page && modo !== "vertical");
  const grupos = useMemo(
    () => pagePairs(total, doblePagina, preferencias?.double_page_offset ?? 0),
    [doblePagina, preferencias?.double_page_offset, total],
  );
  const indiceGrupo = Math.max(0, grupos.findIndex((grupo) => grupo.includes(paginaActual)));
  const paginasVisibles = grupos[indiceGrupo] ?? [];
  const ventana = useMemo(() => decodeWindow(paginaActual, total), [paginaActual, total]);
  const indicesVivos = useMemo(() => new Set(ventana), [ventana]);
  const paginaPorIndice = useMemo(
    () => new Map(paginas.map((pagina) => [pagina.index, pagina])),
    [paginas],
  );
  const indiceCapitulo = capitulos.findIndex((capitulo) => capitulo.source_id === chapter.source_id);
  const capituloAnterior = indiceCapitulo > 0 ? capitulos[indiceCapitulo - 1] : null;
  const capituloSiguiente = indiceCapitulo >= 0 && indiceCapitulo < capitulos.length - 1
    ? capitulos[indiceCapitulo + 1]
    : null;

  const revelarPaginaVertical = useCallback((pagina: number) => {
    requestAnimationFrame(() => {
      contenedorVertical.current
        ?.querySelector<HTMLElement>(`[data-reader-page="${pagina}"]`)
        ?.scrollIntoView({ block: "start" });
    });
  }, []);

  const irAPagina = useCallback((pagina: number, revelar = true) => {
    if (total === 0) return;
    const siguiente = Math.min(total, Math.max(1, pagina));
    setPaginaActual(siguiente);
    if (revelar && modo === "vertical") revelarPaginaVertical(siguiente);
  }, [modo, revelarPaginaVertical, total]);

  const abrirTransicion = useCallback((direccion: "previous" | "next") => {
    const destino = direccion === "next" ? capituloSiguiente : capituloAnterior;
    setTransicion({ direccion, destino });
    if (direccion !== "next" || eventosEmitidos.current.has(chapter.source_id)) return;
    eventosEmitidos.current.add(chapter.source_id);
    // En esta fase NADIE consume la fila. El evento nace antes que su consumidor para
    // que la Fase 5 encuentre el trigger del sync ya persistido, tal como exige D-15.
    void api.createReadingEvent(
      SOURCE_NAME,
      chapter.series_id,
      chapter.source_id,
      chapter.number,
    ).catch((reason: unknown) => setAviso(reason instanceof Error ? reason.message : String(reason)));
  }, [capituloAnterior, capituloSiguiente, chapter.number, chapter.series_id, chapter.source_id]);

  const mover = useCallback((direccion: -1 | 1) => {
    if (grupos.length === 0) return;
    const siguienteGrupo = indiceGrupo + direccion;
    if (siguienteGrupo < 0) {
      abrirTransicion("previous");
      return;
    }
    if (siguienteGrupo >= grupos.length) {
      abrirTransicion("next");
      return;
    }
    const pagina = grupos[siguienteGrupo]?.[0];
    if (pagina != null) irAPagina(pagina);
  }, [abrirTransicion, grupos, indiceGrupo, irAPagina]);

  useEffect(() => {
    if (!listo || total === 0) return;
    const temporizador = window.setTimeout(() => {
      void api.setReaderProgress(SOURCE_NAME, chapter.source_id, paginaActual)
        .catch((reason: unknown) => setAviso(reason instanceof Error ? reason.message : String(reason)));
    }, PROGRESS_DEBOUNCE_MS);
    return () => window.clearTimeout(temporizador);
  }, [chapter.source_id, listo, paginaActual, total]);

  useEffect(() => {
    const cambioAVertical = modo === "vertical" && modoAnterior.current !== "vertical";
    modoAnterior.current = modo ?? null;
    if (!listo || modo !== "vertical" || (scrollInicialHecho.current && !cambioAVertical)) return;

    restaurandoScroll.current = true;
    revelarPaginaVertical(paginaActual);
    scrollInicialHecho.current = true;
    const temporizador = window.setTimeout(() => { restaurandoScroll.current = false; }, 0);
    return () => window.clearTimeout(temporizador);
  }, [listo, modo, paginaActual, revelarPaginaVertical]);

  useEffect(() => {
    const raiz = contenedorVertical.current;
    if (modo !== "vertical" || !raiz) return;
    const observador = new IntersectionObserver((entradas) => {
      if (restaurandoScroll.current) return;
      const visible = entradas
        .filter((entrada) => entrada.isIntersecting)
        .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
      const pagina = Number((visible?.target as HTMLElement | undefined)?.dataset.readerPage);
      if (Number.isInteger(pagina) && pagina >= 1 && pagina <= total) setPaginaActual(pagina);
    }, { root: raiz, threshold: [0.25, 0.5, 0.75] });
    raiz.querySelectorAll<HTMLElement>("[data-reader-page]").forEach((elemento) => observador.observe(elemento));
    return () => observador.disconnect();
  }, [modo, total]);

  // Calienta la cache HTTP de los vecinos de la ventana SIN montarlos: sin elemento vivo no hay
  // layout, ni decode, ni bitmap — que es justo lo que pagaba el preload maquetado a resolucion
  // intrinseca. El `Cache-Control: private, max-age=3600` que sirve el sidecar es lo que permite
  // que la pagina ya calentada pinte desde cache al pasar.
  useEffect(() => {
    // En vertical esas paginas ya estan montadas como <img>: volver a pedirlas seria trabajo duplicado.
    if (modo === "vertical") return;
    const controlador = new AbortController();
    for (const indice of ventana) {
      if (paginasVisibles.includes(indice)) continue;
      const pagina = paginaPorIndice.get(indice);
      if (!pagina) continue;
      // `no-cors` iguala el modo de peticion al del <img> (que tampoco es CORS), asi que la entrada
      // de cache que se escribe es la que el <img> puede reutilizar, y es inmune al origen `null`
      // del renderer empaquetado (file://). Un preload que revienta no debe avisar al usuario.
      void fetch(pagina.url, { mode: "no-cors", signal: controlador.signal }).catch(() => {});
    }
    // Pasar pagina cancela lo que ya no sirve, en vez de apilar peticiones capitulo abajo.
    return () => controlador.abort();
  }, [modo, paginaPorIndice, paginasVisibles, ventana]);

  const alternarPantallaCompleta = useCallback(() => {
    const operacion = document.fullscreenElement
      ? document.exitFullscreen()
      : document.documentElement.requestFullscreen();
    void operacion.catch((reason: unknown) => setAviso(reason instanceof Error ? reason.message : String(reason)));
  }, []);

  useEffect(() => {
    const alPulsar = (event: KeyboardEvent) => {
      const editable = event.target instanceof HTMLInputElement
        || event.target instanceof HTMLSelectElement
        || event.target instanceof HTMLTextAreaElement;
      if (editable && event.key !== "Escape" && event.key !== "F11") return;

      let atendida = true;
      switch (event.key) {
        // El sentido de lectura manda sobre la geometria: en RTL, derecha retrocede.
        // De lo contrario el manga se lee al reves y parece un fallo del scroll.
        case "ArrowRight": mover(modo === "rtl" ? -1 : 1); break;
        case "ArrowLeft": mover(modo === "rtl" ? 1 : -1); break;
        case "PageDown": mover(1); break;
        case "PageUp": mover(-1); break;
        case " ": mover(1); break;
        case "Home": irAPagina(grupos[0]?.[0] ?? 1); break;
        case "End": irAPagina(grupos.at(-1)?.[0] ?? total); break;
        case "Escape": onClose(); break;
        case "F11": alternarPantallaCompleta(); break;
        default: atendida = false;
      }
      if (atendida) event.preventDefault();
    };
    document.addEventListener("keydown", alPulsar);
    return () => document.removeEventListener("keydown", alPulsar);
  }, [alternarPantallaCompleta, grupos, irAPagina, modo, mover, onClose, total]);

  const ajustarZoom = useCallback((delta: number) => {
    setZoom((actual) => {
      const siguiente = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, actual + delta));
      if (siguiente === MIN_ZOOM) setPaneo({ x: 0, y: 0 });
      return siguiente;
    });
  }, []);

  const alUsarRueda = (event: ReactWheelEvent<HTMLDivElement>) => {
    if (event.ctrlKey) {
      event.preventDefault();
      ajustarZoom(event.deltaY < 0 ? ZOOM_STEP : -ZOOM_STEP);
      return;
    }
    if (modo === "vertical") return;
    event.preventDefault();
    if (ruedaBloqueada.current || Math.abs(event.deltaY) + Math.abs(event.deltaX) < 10) return;
    ruedaBloqueada.current = true;
    mover(event.deltaY + event.deltaX > 0 ? 1 : -1);
    window.setTimeout(() => { ruedaBloqueada.current = false; }, 180);
  };

  const iniciarArrastre = (event: ReactMouseEvent<HTMLDivElement>) => {
    if (zoom <= MIN_ZOOM || event.button !== 0) return;
    event.preventDefault();
    huboArrastre.current = false;
    arrastre.current = {
      x: event.clientX,
      y: event.clientY,
      origenX: paneo.x,
      origenY: paneo.y,
    };
  };

  const moverArrastre = (event: ReactMouseEvent<HTMLDivElement>) => {
    if (!arrastre.current) return;
    const deltaX = event.clientX - arrastre.current.x;
    const deltaY = event.clientY - arrastre.current.y;
    if (Math.abs(deltaX) + Math.abs(deltaY) > 3) huboArrastre.current = true;
    setPaneo({ x: arrastre.current.origenX + deltaX, y: arrastre.current.origenY + deltaY });
  };

  const terminarArrastre = () => { arrastre.current = null; };

  const alHacerClick = (event: ReactMouseEvent<HTMLDivElement>) => {
    if (huboArrastre.current) {
      huboArrastre.current = false;
      return;
    }
    const rectangulo = event.currentTarget.getBoundingClientRect();
    const posicion = event.clientX - rectangulo.left;
    if (posicion < rectangulo.width / 3) mover(modo === "rtl" ? 1 : -1);
    else if (posicion > rectangulo.width * 2 / 3) mover(modo === "rtl" ? -1 : 1);
    else setControlesVisibles((visible) => !visible);
  };

  const guardarPreferencias = (cambio: Partial<ReaderPrefs>) => {
    setPreferencias((actuales) => actuales ? { ...actuales, ...cambio } : actuales);
    void api.setReaderPrefs(SOURCE_NAME, chapter.series_id, cambio)
      .catch((reason: unknown) => setAviso(reason instanceof Error ? reason.message : String(reason)));
  };

  if (cargando) {
    return <section className="reader"><p className="reader-status">{t("reader.loading")}</p></section>;
  }
  if (errorCarga || !preferencias) {
    return (
      <section className="reader">
        <div className="reader-status reader-status--error">
          <p>{errorCarga ?? t("reader.error")}</p>
          <button type="button" onClick={onClose}>{t("reader.close")}</button>
        </div>
      </section>
    );
  }
  if (transicion) {
    const termino = transicion.direccion === "next";
    return (
      <section className="reader reader-transition">
        <div className="reader-transition-card">
          <p className="reader-transition-eyebrow">
            {t(termino ? "reader.transition.finished" : "reader.transition.start")}
          </p>
          <h2>{chapter.title}</h2>
          <p>
            {transicion.destino
              ? t(termino ? "reader.transition.next" : "reader.transition.previous")
              : t(termino ? "reader.transition.noNext" : "reader.transition.noPrevious")}
          </p>
          {transicion.destino && <strong>{transicion.destino.title}</strong>}
          <div className="reader-transition-actions">
            <button type="button" onClick={() => setTransicion(null)}>{t("reader.transition.back")}</button>
            {transicion.destino && (
              <button type="button" className="reader-transition-continue" onClick={() => onChapterChange(transicion.destino!)}>
                {t("reader.transition.continue")}
              </button>
            )}
          </div>
        </div>
      </section>
    );
  }

  const ajuste = preferencias.fit ?? "width";
  const transformacion = `translate(${paneo.x}px, ${paneo.y}px) scale(${zoom})`;

  return (
    <section className={`reader reader--${preferencias.mode}`}>
      {controlesVisibles && (
        <header className="reader-controls" onClick={(event) => event.stopPropagation()}>
          <button type="button" onClick={onClose}>{t("reader.close")}</button>
          <strong className="reader-title">{chapter.title}</strong>
          <label>
            {t("reader.mode")}
            <select
              value={preferencias.mode}
              onChange={(event) => guardarPreferencias({ mode: event.target.value as ReaderMode })}
            >
              <option value="rtl">{t("reader.mode.rtl")}</option>
              <option value="ltr">{t("reader.mode.ltr")}</option>
              <option value="vertical">{t("reader.mode.vertical")}</option>
            </select>
          </label>
          <label>
            {t("reader.fit")}
            <select
              value={ajuste}
              onChange={(event) => guardarPreferencias({ fit: event.target.value as ReaderPrefs["fit"] })}
            >
              <option value="width">{t("reader.fit.width")}</option>
              <option value="height">{t("reader.fit.height")}</option>
              <option value="original">{t("reader.fit.original")}</option>
            </select>
          </label>
          {preferencias.mode !== "vertical" && (
            <>
              <label className="reader-check">
                <input
                  type="checkbox"
                  checked={preferencias.double_page}
                  onChange={(event) => guardarPreferencias({ double_page: event.target.checked })}
                />
                {t("reader.doublePage")}
              </label>
              {preferencias.double_page && (
                <label>
                  {t("reader.offset")}
                  <select
                    value={preferencias.double_page_offset === 1 ? 1 : 0}
                    onChange={(event) => guardarPreferencias({ double_page_offset: Number(event.target.value) })}
                  >
                    <option value={0}>{t("reader.offset.none")}</option>
                    <option value={1}>{t("reader.offset.cover")}</option>
                  </select>
                </label>
              )}
            </>
          )}
          <div className="reader-zoom" aria-label={t("reader.zoom")}>
            <button type="button" onClick={() => ajustarZoom(-ZOOM_STEP)} aria-label={t("reader.zoom.out")}>−</button>
            <span>{Math.round(zoom * 100)}%</span>
            <button type="button" onClick={() => ajustarZoom(ZOOM_STEP)} aria-label={t("reader.zoom.in")}>+</button>
            <button type="button" onClick={() => { setZoom(MIN_ZOOM); setPaneo({ x: 0, y: 0 }); }}>{t("reader.zoom.reset")}</button>
          </div>
          <button type="button" onClick={alternarPantallaCompleta}>{t("reader.fullscreen")}</button>
        </header>
      )}

      {/* Fuera del <header>: en que pagina vas es informacion de LECTURA, no un control, y
          ocultar el chrome para leer a gusto no debe costarte saber donde estas (UAT 03,
          hallazgo #5). Mismo patron que .reader-notice, que ya vive aqui por lo mismo. */}
      <span className="reader-counter">{paginaActual} / {total}</span>

      {aviso && <p className="reader-notice">{aviso}</p>}

      {preferencias.mode === "vertical" ? (
        <div
          ref={contenedorVertical}
          className={`reader-stage reader-vertical reader-fit-${ajuste}${zoom > MIN_ZOOM ? " reader-stage--pannable" : ""}`}
          onWheel={alUsarRueda}
          onMouseDown={iniciarArrastre}
          onMouseMove={moverArrastre}
          onMouseUp={terminarArrastre}
          onMouseLeave={terminarArrastre}
          onClick={alHacerClick}
        >
          {Array.from({ length: total }, (_, indice) => indice + 1).map((indice) => {
            const pagina = paginaPorIndice.get(indice);
            return (
              <div key={indice} className="reader-vertical-slot" data-reader-page={indice}>
                {indicesVivos.has(indice) && pagina && (
                  <div className="reader-page reader-page--vertical" style={{ transform: transformacion }}>
                    <img src={pagina.url} alt={pagina.filename} decoding="async" loading="lazy" draggable={false} />
                  </div>
                )}
              </div>
            );
          })}
        </div>
      ) : (
        <div
          className={`reader-stage reader-paged${zoom > MIN_ZOOM ? " reader-stage--pannable" : ""}`}
          onWheel={alUsarRueda}
          onMouseDown={iniciarArrastre}
          onMouseMove={moverArrastre}
          onMouseUp={terminarArrastre}
          onMouseLeave={terminarArrastre}
          onClick={alHacerClick}
        >
          <div
            className={`reader-pages reader-direction-${preferencias.mode} reader-fit-${ajuste}`}
            style={{ transform: transformacion }}
          >
            {paginasVisibles.map((indice) => {
              const pagina = paginaPorIndice.get(indice);
              if (!pagina) return null;
              return (
                <div key={pagina.index} className="reader-page reader-page--visible">
                  <img src={pagina.url} alt={pagina.filename} decoding="async" draggable={false} />
                </div>
              );
            })}
          </div>
        </div>
      )}
    </section>
  );
}
