import { useCallback, useEffect, useState } from "react";
import { open } from "@tauri-apps/plugin-dialog";

import { api } from "./api";
import { useApp } from "./i18n";
import type { LibraryFolder, ScanSummary } from "./types";

export function LibrarySettingsView() {
  const { t } = useApp();
  const [folders, setFolders] = useState<LibraryFolder[]>([]);
  const [summary, setSummary] = useState<ScanSummary | null>(null);
  const [scanning, setScanning] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const message = (reason: unknown): string =>
    reason instanceof Error ? reason.message : t("libset.error");

  const load = useCallback(async () => {
    setFolders(await api.libraryFolders());
  }, []);

  useEffect(() => { void load().catch((reason) => setError(message(reason))); }, [load]);

  const addFolder = async () => {
    setError(null);
    try {
      const selected = await open({ directory: true, multiple: false });
      if (typeof selected !== "string") return;
      setBusy(true);
      await api.addLibraryFolder(selected, true);
      await load();
    } catch (reason) {
      setError(message(reason));
    } finally {
      setBusy(false);
    }
  };

  const toggleRecursive = async (folder: LibraryFolder) => {
    setError(null);
    setBusy(true);
    try {
      await api.addLibraryFolder(folder.path, !folder.recursive);
      await load();
    } catch (reason) {
      setError(message(reason));
    } finally {
      setBusy(false);
    }
  };

  const remove = async (folder: LibraryFolder) => {
    if (!window.confirm(`${t("libset.removeConfirm")} “${folder.path}”?`)) return;
    setError(null);
    setBusy(true);
    try {
      await api.deleteLibraryFolder(folder.id);
      await load();
    } catch (reason) {
      setError(message(reason));
    } finally {
      setBusy(false);
    }
  };

  const scan = async () => {
    setError(null);
    setScanning(true);
    try {
      setSummary(await api.scanLibrary());
    } catch (reason) {
      setError(message(reason));
    } finally {
      setScanning(false);
    }
  };

  const isTauri = "__TAURI_INTERNALS__" in window;

  return <section className="account-settings">
    <div className="account-heading">
      <div>
        <h2>{t("libset.title")}</h2>
        <p>{t("libset.d")}</p>
      </div>
      <button className="primary small" disabled={busy || !isTauri} onClick={() => void addFolder()}>{t("libset.addFolder")}</button>
    </div>

    {error && <div className="modal-error">{error}</div>}
    {!isTauri && <p className="preference-readonly">{t("libset.desktopOnly")}</p>}

    <div className="folder-list">
      {folders.map((folder) => (
        <article key={folder.id} className="folder-item">
          <div className="folder-path"><strong title={folder.path}>{folder.path}</strong></div>
          <label className="checkbox-field"><input type="checkbox" checked={folder.recursive} disabled={busy} onChange={() => void toggleRecursive(folder)} /> {t("libset.recursive")}</label>
          <button className="danger small" disabled={busy} onClick={() => void remove(folder)}>{t("libset.remove")}</button>
        </article>
      ))}
      {folders.length === 0 && <p className="account-empty">{t("libset.empty")}</p>}
    </div>

    <div className="sync-settings">
      <div>
        <h2>{t("libset.scanTitle")}</h2>
        <p>{summary
          ? `${summary.matched} ${t("libset.scanOf")} ${summary.total} ${t("libset.scanMatched")} (${summary.unmatched} ${t("libset.scanUnmatched")}).`
          : t("libset.scanHint")}</p>
      </div>
      <button className="primary" disabled={scanning || folders.length === 0} onClick={() => void scan()}>{scanning ? t("libset.scanning") : t("libset.scanNow")}</button>
    </div>
  </section>;
}
