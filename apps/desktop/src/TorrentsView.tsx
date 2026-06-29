import { useEffect, useState } from "react";
import { openUrl } from "@tauri-apps/plugin-opener";
import { useApp } from "./i18n";
import { api } from "./api";
import type { TorrentItem } from "./types";

export function TorrentsView() {
  const { t } = useApp();
  const [items, setItems] = useState<TorrentItem[]>([]);
  const [loading, setLoading] = useState(false);

  const load = async (refresh: boolean) => {
    setLoading(true);
    try { setItems(await api.torrentFeed(refresh)); }
    finally { setLoading(false); }
  };
  // ponytail: load is stable (no captured state), deps array left empty intentionally
  useEffect(() => { void load(false); }, []);

  const onDownload = async (it: TorrentItem) => {
    const res = await api.downloadTorrent(it.signature);
    if (res.action === "magnet" && res.link) await openUrl(res.link);
    setItems((prev) => prev.filter((x) => x.signature !== it.signature));
  };
  const onDiscard = async (it: TorrentItem) => {
    await api.discardTorrent(it.signature);
    setItems((prev) => prev.filter((x) => x.signature !== it.signature));
  };

  return (
    <section className="torrents-view">
      <header className="torrents-header">
        <h2>{t("torrents.title")}</h2>
        <button onClick={() => void load(true)} disabled={loading}>
          {loading ? t("torrents.refreshing") : t("torrents.refresh")}
        </button>
      </header>
      {items.length === 0 && !loading && <p className="empty">{t("torrents.empty")}</p>}
      <ul className="torrents-list">
        {items.map((it) => (
          <li key={it.signature} className={it.is_new ? "new" : ""}>
            <div className="t-main">
              <span className="t-title">{it.media_title ?? it.raw_title}</span>
              {it.episode != null && <span className="t-ep">#{it.episode}</span>}
              {it.resolution && <span className="t-res">{it.resolution}</span>}
              {it.group && <span className="t-group">{it.group}</span>}
              {it.seeders != null && <span className="t-seed">▲{it.seeders}</span>}
            </div>
            <div className="t-actions">
              <button onClick={() => void onDownload(it)}>{t("torrents.download")}</button>
              <button onClick={() => void onDiscard(it)}>{t("torrents.discard")}</button>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
