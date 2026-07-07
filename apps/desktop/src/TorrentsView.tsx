import { useEffect, useMemo, useState } from "react";
import { openUrl } from "@tauri-apps/plugin-opener";
import { useApp } from "./i18n";
import { api } from "./api";
import { useContextMenu, type CtxItem } from "./ContextMenu";
import type { TorrentItem } from "./types";

type TorrentGroup = { key: string; title: string; cover: string | null; items: TorrentItem[] };

export function TorrentsView() {
  const { t } = useApp();
  const [items, setItems] = useState<TorrentItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = async (refresh: boolean) => {
    setLoading(true);
    setError(null);
    try { setItems(await api.torrentFeed(refresh)); }
    catch (reason) { setError(reason instanceof Error ? reason.message : t("torrents.downloadError")); }
    finally { setLoading(false); }
  };
  // ponytail: load is stable (no captured state), deps array left empty intentionally
  useEffect(() => { void load(false); }, []);

  // Una tarjeta por serie: mismas media agrupadas bajo un solo portrait.
  const groups = useMemo(() => {
    const map = new Map<string, TorrentGroup>();
    for (const it of items) {
      const key = it.media_id != null ? `m${it.media_id}` : (it.media_title ?? it.raw_title);
      let group = map.get(key);
      if (!group) {
        group = { key, title: it.media_title ?? it.raw_title, cover: it.cover_image ?? null, items: [] };
        map.set(key, group);
      }
      group.items.push(it);
    }
    return [...map.values()];
  }, [items]);

  const onDownload = async (it: TorrentItem, mode: "magnet" | "torrent") => {
    setError(null);
    try {
      const res = await api.downloadTorrent(it.signature, mode);
      if (res.action === "magnet" && res.link) await openUrl(res.link);
      setItems((prev) => prev.filter((x) => x.signature !== it.signature));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : t("torrents.downloadError"));
    }
  };
  const onDiscard = async (it: TorrentItem) => {
    await api.discardTorrent(it.signature);
    setItems((prev) => prev.filter((x) => x.signature !== it.signature));
  };

  const { openMenu, menu } = useContextMenu();
  const torrentMenu = (it: TorrentItem): CtxItem[] => [
    { label: t("torrents.magnet"), onClick: () => void onDownload(it, "magnet") },
    { label: t("torrents.file"), onClick: () => void onDownload(it, "torrent") },
    { label: t("torrents.discard"), danger: true, onClick: () => void onDiscard(it) },
    { sep: true },
    {
      label: t("ctx.moreTorrents"),
      onClick: () => void openUrl(`https://nyaa.si/?f=0&c=1_2&q=${encodeURIComponent(it.media_title ?? it.raw_title)}`),
    },
  ];

  return (
    <section className="torrents-view">
      <header className="torrents-header">
        <h2>{t("torrents.title")}</h2>
        <button onClick={() => void load(true)} disabled={loading}>
          {loading ? t("torrents.refreshing") : t("torrents.refresh")}
        </button>
      </header>
      {error && <p className="torrents-error">{error}</p>}
      {items.length === 0 && !loading && <p className="empty">{t("torrents.empty")}</p>}
      {groups.map((group) => (
        <article key={group.key} className="torrent-group">
          <div className="tg-poster" style={group.cover ? { backgroundImage: `url(${group.cover})` } : undefined} />
          <div className="tg-body">
            <h3 title={group.title}>{group.title}</h3>
            <div className="tg-table-wrap">
              <table className="tg-table">
                <thead>
                  <tr>
                    <th>{t("torrents.col.episode")}</th>
                    <th>{t("torrents.col.quality")}</th>
                    <th>{t("torrents.col.fansub")}</th>
                    <th>{t("torrents.col.seeds")}</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {group.items.map((it) => (
                    <tr
                      key={it.signature}
                      className={it.is_new ? "new" : ""}
                      title={it.raw_title}
                      onContextMenu={(e) => openMenu(e, torrentMenu(it))}
                    >
                      <td>{it.episode != null ? `#${it.episode}` : "—"}</td>
                      <td>{it.resolution ?? "—"}</td>
                      <td>{it.group ?? "—"}</td>
                      <td>{it.seeders ?? "—"}</td>
                      <td className="tg-actions">
                        <button title={t("torrents.magnet")} onClick={() => void onDownload(it, "magnet")}>🧲</button>
                        <button title={t("torrents.file")} onClick={() => void onDownload(it, "torrent")}>⬇</button>
                        <button title={t("torrents.discard")} onClick={() => void onDiscard(it)}>✕</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </article>
      ))}
      {menu}
    </section>
  );
}
