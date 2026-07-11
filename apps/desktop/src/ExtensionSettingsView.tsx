import { useCallback, useEffect, useState } from "react";
import { native } from "./native";

import { api } from "./api";
import { useApp } from "./i18n";
import type { ExtensionBundle, ExtensionClientInfo } from "./types";

export function ExtensionSettingsView() {
  const { t, lang } = useApp();
  const [clients, setClients] = useState<ExtensionClientInfo[]>([]);
  const [bundle, setBundle] = useState<ExtensionBundle | null>(null);
  const [error, setError] = useState<string | null>(null);

  const formatDate = (timestamp: number | null): string =>
    timestamp ? new Date(timestamp * 1000).toLocaleString(lang) : t("ext.never");

  const load = useCallback(async () => {
    setClients(await api.extensionClients());
    setBundle(await api.extensionBundle().catch(() => null));
  }, []);

  // Reintenta al recuperar el foco: si la carga inicial pilló al backend
  // reiniciándose (hot-reload de dev), la lista se quedaba vacía para siempre.
  useEffect(() => {
    void load().catch(() => {});
    const refresh = () => void load().catch(() => {});
    window.addEventListener("focus", refresh);
    return () => window.removeEventListener("focus", refresh);
  }, [load]);

  const openFolder = async (path: string | null) => {
    if (!path) return;
    setError(null);
    try {
      await native.revealItemInDir(path);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : t("ext.openError"));
    }
  };

  const revoke = async (client: ExtensionClientInfo) => {
    if (!window.confirm(`${t("ext.revokeConfirm")} ${client.label}?`)) return;
    try {
      await api.revokeExtensionClient(client.id);
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : t("ext.revokeError"));
    }
  };

  const built = Boolean(bundle && (bundle.chromium || bundle.firefox));

  return <section className="extension-settings">
    <div className="extension-heading"><div><h2>{t("ext.title")}</h2><p>{t("ext.d")}</p></div></div>

    <div className="extension-install">
      <h3>{t("ext.install")}</h3>
      {!built ? (
        <p className="extension-hint">{t("ext.buildFirst")} <code>npm run build</code> · <code>apps/extension</code>.</p>
      ) : <>
        <div className="extension-install-browser">
          <div>
            <strong>Chrome · Edge · Brave</strong>
            <ol><li>{t("ext.open")} <code>chrome://extensions</code></li><li>{t("ext.chromeDevMode")}</li><li>{t("ext.chromeLoad")}</li></ol>
          </div>
          <button className="primary" disabled={!bundle?.chromium} onClick={() => void openFolder(bundle?.chromium ?? null)}>{t("ctx.openFolder")}</button>
        </div>
        <div className="extension-install-browser">
          <div>
            <strong>Firefox</strong>
            <ol><li>{t("ext.open")} <code>about:debugging#/runtime/this-firefox</code></li><li>{t("ext.firefoxLoad")}</li><li>{t("ext.firefoxManifest")} <code>manifest.json</code></li></ol>
          </div>
          <button className="primary" disabled={!bundle?.firefox} onClick={() => void openFolder(bundle?.firefox ?? null)}>{t("ctx.openFolder")}</button>
        </div>
        <p className="extension-hint">{t("ext.pairHint")}</p>
      </>}
    </div>

    {error && <div className="modal-error">{error}</div>}
    <div className="extension-clients">{clients.filter((client) => !client.revoked_at).map((client) => <article key={client.id}><div><strong>{client.label}</strong><span>{t("ext.lastEvent")} {formatDate(client.last_seen_at)} · {t("ext.expires")} {formatDate(client.expires_at)}</span></div><button className="danger" onClick={() => void revoke(client)}>{t("ext.revoke")}</button></article>)}{!clients.some((client) => !client.revoked_at) && <p>{t("ext.noClients")}</p>}</div>
  </section>;
}
