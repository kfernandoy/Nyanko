import { useEffect, useState } from "react";
import { api } from "./api";
import { useApp } from "./i18n";
import type { MangaChapter } from "./types";

const SOURCE_NAME = "local_archive";

type NodoNavegacion = {
  id: string;
  title: string;
};

export function MangaLibraryView({ onOpenChapter }: { onOpenChapter: (chapter: MangaChapter) => void }) {
  const { t } = useApp();
  const [capitulos, setCapitulos] = useState<MangaChapter[]>([]);
  const [ruta, setRuta] = useState<NodoNavegacion[]>([]);
  const [cargando, setCargando] = useState(true);
  const [sinCarpetas, setSinCarpetas] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelado = false;

    const cargar = async () => {
      setCargando(true);
      setError(null);
      try {
        const nodoActual = ruta[ruta.length - 1];
        if (nodoActual) {
          const hijos = await api.mangaChapters(SOURCE_NAME, nodoActual.id);
          if (!cancelado) {
            setCapitulos(hijos);
            setSinCarpetas(false);
          }
          return;
        }

        // `libraryFolders()` devuelve TODAS las carpetas a proposito (Ajustes las lista
        // todas), asi que el filtro por tipo es cosa de quien consume: pedirle capitulos
        // de manga a una carpeta de anime da «Raiz local no registrada», y como esto es
        // un Promise.all, esa unica raiz invalida tumbaba la biblioteca ENTERA. Mismo
        // criterio que `LocalArchiveSource._load_roots`: sin tipo ⇒ ambas.
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
        const raices = await Promise.all(
          carpetas.map((carpeta) => api.mangaChapters(SOURCE_NAME, `${carpeta.id}:.`)),
        );
        if (!cancelado) {
          setCapitulos(raices.flat());
          setSinCarpetas(false);
        }
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

  const abrir = (capitulo: MangaChapter) => {
    if (capitulo.is_chapter) {
      onOpenChapter(capitulo);
      return;
    }
    setRuta((actual) => [...actual, { id: capitulo.source_id, title: capitulo.title }]);
  };

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
          {capitulos.map((capitulo) => (
            <button key={capitulo.source_id} className="manga-library-item" onClick={() => abrir(capitulo)}>
              <span className="manga-library-number">
                {capitulo.number != null ? `${t("manga.chapter")} ${capitulo.number}` : ""}
              </span>
              <strong className="manga-library-title">{capitulo.title}</strong>
              {!capitulo.is_chapter && <span className="manga-library-chevron" aria-hidden="true">›</span>}
            </button>
          ))}
        </div>
      )}
    </section>
  );
}
