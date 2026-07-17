import { useEffect, useState } from "react";
import { api } from "./api";
import { useApp } from "./i18n";
import type { MangaChapter, MangaLink, MangaLinkMatch, MediaItem } from "./types";

const SOURCE_NAME = "local_archive";

type NodoNavegacion = {
  id: string;
  title: string;
};

export function MangaLibraryView({ onOpenChapter }: { onOpenChapter: (chapter: MangaChapter) => void }) {
  const { t, lang } = useApp();
  const [capitulos, setCapitulos] = useState<MangaChapter[]>([]);
  const [ruta, setRuta] = useState<NodoNavegacion[]>([]);
  const [vinculos, setVinculos] = useState<Record<string, MangaLink | null | undefined>>({});
  const [serieAbierta, setSerieAbierta] = useState<MangaChapter | null>(null);
  const [propuesta, setPropuesta] = useState<MangaLinkMatch | null>(null);
  const [idSeleccionado, setIdSeleccionado] = useState<number | null>(null);
  const [desfaseCapitulos, setDesfaseCapitulos] = useState(0);
  const [cargandoPanel, setCargandoPanel] = useState(false);
  const [guardandoVinculo, setGuardandoVinculo] = useState(false);
  const [errorVinculo, setErrorVinculo] = useState<string | null>(null);
  const [cargando, setCargando] = useState(true);
  const [sinCarpetas, setSinCarpetas] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelado = false;

    const cargar = async () => {
      setCargando(true);
      setError(null);
      setVinculos({});
      try {
        const cargarVinculos = async (nodos: MangaChapter[]) => {
          const series = nodos.filter((nodo) => !nodo.is_chapter);
          const resultados = await Promise.allSettled(
            series.map((nodo) => (
              // En chapters(), local_archive.py:120-122 distingue el nodo de su padre:
              // la clave de una serie es su source_id, nunca su series_id compartido.
              api.mangaLink(SOURCE_NAME, nodo.source_id)
            )),
          );
          if (cancelado) return;
          const siguientes: Record<string, MangaLink | null | undefined> = {};
          resultados.forEach((resultado, indice) => {
            if (resultado.status === "fulfilled") {
              siguientes[series[indice].source_id] = resultado.value;
            }
          });
          setVinculos(siguientes);
        };

        const nodoActual = ruta[ruta.length - 1];
        if (nodoActual) {
          const hijos = await api.mangaChapters(SOURCE_NAME, nodoActual.id);
          if (!cancelado) {
            setCapitulos(hijos);
            setSinCarpetas(false);
          }
          await cargarVinculos(hijos);
          return;
        }

        // `libraryFolders()` devuelve TODAS las carpetas a proposito (Ajustes las lista
        // todas), asi que el filtro por tipo es cosa de quien consume: pedirle capitulos
        // de manga a una carpeta de anime da «Raiz local no registrada». Promise.allSettled
        // conserva el resto de la biblioteca si una raiz valida falla por separado.
        const carpetas = (await api.libraryFolders()).filter(
          (carpeta) => (carpeta.kind ?? "ambas") !== "anime",
        );
        if (carpetas.length === 0) {
          if (!cancelado) {
            setCapitulos([]);
            setSinCarpetas(true);
          }
          return;
        }
        const resultadosRaices = await Promise.allSettled(
          carpetas.map((carpeta) => api.mangaChapters(SOURCE_NAME, `${carpeta.id}:.`)),
        );
        const raices = resultadosRaices.flatMap((resultado) => (
          resultado.status === "fulfilled" ? resultado.value : []
        ));
        if (!cancelado) {
          setCapitulos(raices);
          setSinCarpetas(false);
        }
        await cargarVinculos(raices);
      } catch (razon) {
        if (!cancelado) {
          setCapitulos([]);
          setSinCarpetas(false);
          setError(razon instanceof Error ? razon.message : t("manga.error"));
        }
      } finally {
        if (!cancelado) setCargando(false);
      }
    };

    void cargar();
    return () => { cancelado = true; };
  }, [ruta, t]);

  useEffect(() => {
    if (!serieAbierta) return;
    let cancelado = false;
    setCargandoPanel(true);
    setErrorVinculo(null);
    setPropuesta(null);

    api.mangaLinkMatch(SOURCE_NAME, serieAbierta.source_id)
      .then((resultado) => {
        if (cancelado) return;
        setPropuesta(resultado);
        setIdSeleccionado(resultado.link?.media_id ?? resultado.match?.id ?? resultado.suggestions[0]?.id ?? null);
        setDesfaseCapitulos(resultado.link?.chapter_offset ?? 0);
      })
      .catch((razon) => {
        if (!cancelado) {
          setVinculos((actuales) => ({ ...actuales, [serieAbierta.source_id]: undefined }));
          setErrorVinculo(razon instanceof Error ? razon.message : t("manga.link.loadError"));
        }
      })
      .finally(() => { if (!cancelado) setCargandoPanel(false); });

    return () => { cancelado = true; };
  }, [serieAbierta, t]);

  const abrir = (capitulo: MangaChapter) => {
    if (capitulo.is_chapter) {
      onOpenChapter(capitulo);
      return;
    }
    setRuta((actual) => [...actual, { id: capitulo.source_id, title: capitulo.title }]);
  };

  const confirmarVinculo = async () => {
    if (!serieAbierta || idSeleccionado == null) return;
    setGuardandoVinculo(true);
    setErrorVinculo(null);
    try {
      await api.setMangaLink(
        SOURCE_NAME,
        serieAbierta.source_id,
        idSeleccionado,
        desfaseCapitulos,
      );
      const vigente = await api.mangaLink(SOURCE_NAME, serieAbierta.source_id);
      setVinculos((actuales) => ({ ...actuales, [serieAbierta.source_id]: vigente }));
      setSerieAbierta(null);
    } catch (razon) {
      setErrorVinculo(razon instanceof Error ? razon.message : t("manga.link.saveError"));
    } finally {
      setGuardandoVinculo(false);
    }
  };

  const desvincular = async () => {
    if (!serieAbierta) return;
    setGuardandoVinculo(true);
    setErrorVinculo(null);
    try {
      await api.deleteMangaLink(SOURCE_NAME, serieAbierta.source_id);
      const vigente = await api.mangaLink(SOURCE_NAME, serieAbierta.source_id);
      setVinculos((actuales) => ({ ...actuales, [serieAbierta.source_id]: vigente }));
      setSerieAbierta(null);
    } catch (razon) {
      setErrorVinculo(razon instanceof Error ? razon.message : t("manga.link.saveError"));
    } finally {
      setGuardandoVinculo(false);
    }
  };

  const cambiarVinculo = async () => {
    if (!serieAbierta || !window.confirm(t("manga.link.changeConfirm"))) return;
    setGuardandoVinculo(true);
    setCargandoPanel(true);
    setErrorVinculo(null);
    try {
      // El matcher respeta el vinculo vigente y no propone alternativas hasta borrarlo;
      // este borrado solo ocurre tras el gesto explicito de cambiar del usuario.
      await api.deleteMangaLink(SOURCE_NAME, serieAbierta.source_id);
      setVinculos((actuales) => ({ ...actuales, [serieAbierta.source_id]: null }));
      setPropuesta(null);
      const resultado = await api.mangaLinkMatch(SOURCE_NAME, serieAbierta.source_id);
      setPropuesta(resultado);
      setIdSeleccionado(resultado.match?.id ?? resultado.suggestions[0]?.id ?? null);
      setDesfaseCapitulos(0);
    } catch (razon) {
      setErrorVinculo(razon instanceof Error ? razon.message : t("manga.link.saveError"));
    } finally {
      setGuardandoVinculo(false);
      setCargandoPanel(false);
    }
  };

  const opciones: MediaItem[] = propuesta
    ? [propuesta.match, ...propuesta.suggestions].filter((opcion): opcion is MediaItem => opcion != null)
    : [];
  const desfaseValido = desfaseCapitulos >= -9999 && desfaseCapitulos <= 9999;

  return (
    <section className="manga-library">
      <header className="manga-library-header">
        {ruta.length > 0 && (
          <button className="manga-library-back" onClick={() => setRuta((actual) => actual.slice(0, -1))}>
            ← {t("manga.back")}
          </button>
        )}
        <div className="manga-library-breadcrumb" role="navigation" aria-label={t("manga.breadcrumb")}>
          <button onClick={() => setRuta([])} aria-current={ruta.length === 0 ? "page" : undefined}>
            {t("manga.root")}
          </button>
          {ruta.map((nodo, indice) => (
            <span key={nodo.id}>
              <i aria-hidden="true">/</i>
              <button
                onClick={() => setRuta((actual) => actual.slice(0, indice + 1))}
                aria-current={indice === ruta.length - 1 ? "page" : undefined}
              >
                {nodo.title}
              </button>
            </span>
          ))}
        </div>
      </header>

      {cargando && <p className="manga-library-state">{t("manga.loading")}</p>}
      {!cargando && error && <p className="manga-library-state manga-library-error" role="alert">{error}</p>}
      {!cargando && !error && capitulos.length === 0 && (
        <p className="manga-library-state">{t(sinCarpetas ? "manga.empty" : "manga.noResults")}</p>
      )}
      {!cargando && !error && capitulos.length > 0 && (
        <div className="manga-library-list">
          {capitulos.map((capitulo, indice) => {
            const vinculo = vinculos[capitulo.source_id];
            const panelAbierto = serieAbierta?.source_id === capitulo.source_id;
            const panelId = `manga-link-panel-${indice}`;
            return (
              <div key={capitulo.source_id} className="manga-library-entry">
                <div className="manga-library-item">
                  <button type="button" className="manga-library-open" onClick={() => abrir(capitulo)}>
                    <span className="manga-library-number">
                      {capitulo.number != null ? `${t("manga.chapter")} ${capitulo.number}` : ""}
                    </span>
                    <strong className="manga-library-title">{capitulo.title}</strong>
                    {!capitulo.is_chapter && <span className="manga-library-chevron" aria-hidden="true">›</span>}
                  </button>
                  {!capitulo.is_chapter && (
                    <button
                      type="button"
                      className="manga-library-link"
                      onClick={() => setSerieAbierta(capitulo)}
                      aria-expanded={panelAbierto}
                      aria-controls={panelId}
                    >
                      <span className="manga-library-link-status">
                        {vinculo === undefined
                          ? ""
                          : vinculo
                            ? `${t("manga.link.linked")}: ${vinculo.title ?? t("manga.link.unknownTitle")}`
                            : t("manga.link.unlinked")}
                      </span>
                      <strong>{t(vinculo ? "manga.link.change" : "manga.link.open")}</strong>
                    </button>
                  )}
                </div>

                {panelAbierto && (
                  <aside id={panelId} className="manga-library-link-panel" aria-label={t("manga.link.panel")}>
                    <header className="manga-library-link-header">
                      <div>
                        <span className="eyebrow">{t("manga.link.panel")}</span>
                        <h3>{capitulo.title}</h3>
                      </div>
                      <button
                        type="button"
                        onClick={() => setSerieAbierta(null)}
                        disabled={guardandoVinculo}
                        aria-label={t("manga.link.close")}
                      >
                        {t("manga.link.close")}
                      </button>
                    </header>

                    {cargandoPanel && <p className="manga-library-link-message">{t("manga.link.loading")}</p>}
                    {!cargandoPanel && errorVinculo && <p className="manga-library-link-error" role="alert">{errorVinculo}</p>}

                    {!cargandoPanel && !errorVinculo && propuesta?.link && (
                      <div className="manga-library-link-current">
                        <span>{t("manga.link.current")}</span>
                        <strong>{propuesta.link.title ?? t("manga.link.unknownTitle")}</strong>
                        <small>{t("manga.link.offset")}: {propuesta.link.chapter_offset}</small>
                        <div className="manga-library-link-actions">
                          <button type="button" className="danger" onClick={() => void desvincular()} disabled={guardandoVinculo}>
                            {t("manga.link.unlink")}
                          </button>
                          <button type="button" onClick={() => void cambiarVinculo()} disabled={guardandoVinculo}>
                            {t("manga.link.change")}
                          </button>
                        </div>
                      </div>
                    )}

                    {!cargandoPanel && !errorVinculo && propuesta && !propuesta.link && (
                      <div className="manga-library-link-proposal">
                        {propuesta.match && (
                          <p className="manga-library-link-score">
                            <span>{t("manga.link.score")}</span>
                            <strong>{new Intl.NumberFormat(lang, { style: "percent", maximumFractionDigits: 0 }).format(propuesta.match_score)}</strong>
                          </p>
                        )}

                        {opciones.length > 0 ? (
                          <>
                            <fieldset className="manga-library-link-options">
                              <legend>{t("manga.link.options")}</legend>
                              {opciones.map((opcion) => (
                                <label key={opcion.id} className={idSeleccionado === opcion.id ? "is-selected" : ""}>
                                  <input
                                    type="radio"
                                    name="manga-link-option"
                                    checked={idSeleccionado === opcion.id}
                                    onChange={() => setIdSeleccionado(opcion.id)}
                                  />
                                  <strong>{opcion.title}</strong>
                                </label>
                              ))}
                            </fieldset>
                            <label className="manga-library-link-offset">
                              <span>{t("manga.link.offset")}</span>
                              <input
                                type="number"
                                min={-9999}
                                max={9999}
                                value={desfaseCapitulos}
                                onChange={(evento) => setDesfaseCapitulos(Number(evento.target.value))}
                              />
                              <small>{t("manga.link.offsetHelp").replace("{chapter}", String(1 + desfaseCapitulos))}</small>
                            </label>
                            <button
                              type="button"
                              className="manga-library-link-confirm"
                              onClick={() => void confirmarVinculo()}
                              disabled={idSeleccionado == null || !desfaseValido || guardandoVinculo}
                            >
                              {t("manga.link.confirm")}
                            </button>
                          </>
                        ) : (
                          <div className="manga-library-link-empty">
                            <strong>{t("manga.link.noMatches")}</strong>
                            <p>{t("manga.link.noMatchesHelp")}</p>
                          </div>
                        )}
                      </div>
                    )}
                  </aside>
                )}
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}
