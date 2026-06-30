import { useEffect, useState } from "react";
import { useApp } from "./i18n";
import { api } from "./api";
import type { LocalSeries } from "./types";

export function LocalLibraryView({ onBack }: { onBack: () => void }) {
  const { t } = useApp();
  const [items, setItems] = useState<LocalSeries[]>([]);
  const [loading, setLoading] = useState(true);
  useEffect(() => { void api.getLocalLibrary().then((d) => setItems(d)).catch(() => {}).finally(() => setLoading(false)); }, []);
  return (
    <section className="local-library">
      <header className="local-library-header">
        <button className="small" onClick={onBack}>← {t("local.back")}</button>
        <h2>{t("local.title")}</h2>
      </header>
      {loading && <p className="empty">{t("local.loading")}</p>}
      {!loading && items.length === 0 && <p className="empty">{t("local.empty")}</p>}
      <ul className="local-list">
        {items.map((s, i) => (
          <li key={s.media_id ?? `u-${i}`} className={s.matched ? "matched" : "unmatched"}>
            <span className="l-title">{s.title}</span>
            <span className="l-count">{s.episode_count} {t("local.episodes")}</span>
            {!s.matched && <span className="l-tag">{t("local.unmatched")}</span>}
          </li>
        ))}
      </ul>
    </section>
  );
}
