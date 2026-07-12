import { useCallback, useEffect, useState } from "react";
import { native } from "./native";

import { api } from "./api";
import { useApp } from "./i18n";
import type { AccountInfo } from "./types";

const PROVIDERS: { id: string; label: string }[] = [
  { id: "anilist", label: "AniList" },
  { id: "mal", label: "MyAnimeList" },
  { id: "kitsu", label: "Kitsu" },
];

const SIGNUP_URLS: Record<string, string> = {
  anilist: "https://anilist.co/signup",
  mal: "https://myanimelist.net/register.php",
  kitsu: "https://kitsu.app/",
};

type Profile = { username: string; avatar: string | null };

function accountError(reason: unknown): string {
  return reason instanceof Error ? reason.message : "No se pudo actualizar la cuenta";
}

function providerLabel(id: string): string {
  return PROVIDERS.find((p) => p.id === id)?.label ?? id;
}

export function AccountSettingsView({
  activeAccount,
  onConnect,
  onAccountChanged,
  generalExtras,
  providerExtras,
  accountTab,
  onAccountTabChange,
}: {
  activeAccount: { provider: string; alias: string };
  onConnect: (provider: string, alias: string) => Promise<void>;
  onAccountChanged: (provider: string, alias: string) => Promise<void>;
  generalExtras?: React.ReactNode;
  providerExtras?: (providerId: string) => React.ReactNode;
  accountTab?: string;
  onAccountTabChange?: (tab: string) => void;
}) {
  const { t } = useApp();
  const [accounts, setAccounts] = useState<AccountInfo[]>([]);
  const [profiles, setProfiles] = useState<Record<string, Profile>>({});
  const [localTab, setLocalTab] = useState<string>("general");
  const tab = accountTab ?? localTab;
  const setTab = onAccountTabChange ?? setLocalTab;
  const [saving, setSaving] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [kitsuForm, setKitsuForm] = useState(false);
  const [kitsuUser, setKitsuUser] = useState("");
  const [kitsuPass, setKitsuPass] = useState("");

  const load = useCallback(async () => {
    setAccounts(await api.accounts());
  }, []);

  useEffect(() => {
    void load().catch((reason) => setError(accountError(reason)));
    const refresh = () => void load().catch(() => {});
    window.addEventListener("focus", refresh);
    return () => window.removeEventListener("focus", refresh);
  }, [load]);

  // Cada proveedor conectado trae su propio perfil (username/avatar) y se conserva,
  // independientemente de cuál sea el activo.
  useEffect(() => {
    for (const account of accounts) {
      if (!account.authenticated || profiles[account.provider]) continue;
      void api.preferences({ provider: account.provider, alias: account.alias })
        .then(({ data }) => setProfiles((prev) => ({
          ...prev,
          [account.provider]: { username: data.username || "", avatar: data.avatar || null },
        })))
        .catch(() => {});
    }
  }, [accounts, profiles]);

  const makePrimary = async (account: AccountInfo) => {
    setSaving(account.id);
    setError(null);
    setMessage(null);
    try {
      await api.updateAccount(account.id, { is_primary: true });
      await load();
      await onAccountChanged(account.provider, account.alias);
      setMessage(`${providerLabel(account.provider)} ${t("acc.nowPrimary")}`);
    } catch (reason) {
      setError(accountError(reason));
    } finally {
      setSaving(null);
    }
  };

  const disconnect = async (account: AccountInfo) => {
    if (!window.confirm(`¿Desconectar la cuenta de ${providerLabel(account.provider)}?`)) return;
    setSaving(account.id);
    try {
      await api.logoutAccount(account.provider, account.alias);
      const replacement = accounts.find(
        (candidate) => candidate.id !== account.id
          && candidate.provider === account.provider
          && candidate.authenticated,
      );
      if (account.is_primary && replacement) {
        await api.updateAccount(replacement.id, { is_primary: true });
      }
      setProfiles((prev) => { const next = { ...prev }; delete next[account.provider]; return next; });
      await load();
      await onAccountChanged(
        account.provider,
        account.is_primary ? (replacement?.alias ?? "default") : account.alias,
      );
    } catch (reason) {
      setError(accountError(reason));
    } finally {
      setSaving(null);
    }
  };

  const connectKitsu = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setMessage(null);
    setSaving(-1);
    try {
      await api.kitsuConnect(kitsuUser, kitsuPass);
      await load();
      await onAccountChanged("kitsu", "default");
      setKitsuForm(false);
      setKitsuUser("");
      setKitsuPass("");
      setMessage("Kitsu conectado correctamente.");
    } catch (reason) {
      setError(accountError(reason));
    } finally {
      setSaving(null);
    }
  };

  const authedProviders = PROVIDERS.filter((p) => accounts.some((a) => a.provider === p.id && a.authenticated));
  const primaryProvider = accounts.find((a) => a.is_primary && a.authenticated)?.provider ?? activeAccount.provider;

  const selectPrimary = (provider: string) => {
    const account = accounts.find((a) => a.provider === provider && a.is_primary && a.authenticated)
      ?? accounts.find((a) => a.provider === provider && a.authenticated);
    if (account) void makePrimary(account);
  };

  const renderProviderPanel = (prov: string) => {
    const account = accounts.find((a) => a.provider === prov);
    const profile = profiles[prov];
    const isPrimary = Boolean(account?.is_primary && account.authenticated);
    return (
      <div className="provider-panel">
        <div className="provider-panel-head">
          <h3>{providerLabel(prov)}</h3>
          {isPrimary && <span className="badge-active">Principal</span>}
        </div>
        {!account || !account.authenticated ? (
          <div className="provider-connect">
            <p>{account?.has_credential_ref ? t("acc.expired") : `${t("acc.connect")} ${providerLabel(prov)}.`}</p>
            {prov === "kitsu"
              ? (kitsuForm
                ? <form className="kitsu-login-form" onSubmit={(e) => void connectKitsu(e)}>
                    <input type="email" placeholder="Email de Kitsu" required value={kitsuUser} onChange={(e) => setKitsuUser(e.target.value)} autoComplete="username" />
                    <input type="password" placeholder="Contraseña" required value={kitsuPass} onChange={(e) => setKitsuPass(e.target.value)} autoComplete="current-password" />
                    <button type="submit" className="primary small" disabled={saving === -1}>{t("acc.connectBtn")}</button>
                    <button type="button" className="small" onClick={() => setKitsuForm(false)}>{t("acc.cancel")}</button>
                  </form>
                : <button className="primary small" onClick={() => setKitsuForm(true)}>{account?.has_credential_ref ? t("acc.reconnect") : t("acc.auth")}</button>)
              : <button className="primary small" onClick={() => void onConnect(prov, account?.alias ?? "default")}>{account?.has_credential_ref ? t("acc.reconnect") : t("acc.auth")}</button>
            }
            <p className="signup-hint">
              {t("acc.noAccount")}{" "}
              <button className="link-button" onClick={() => void native.openExternal(SIGNUP_URLS[prov]).catch(() => {})}>
                {t("acc.createOn")} {providerLabel(prov)}
              </button>
            </p>
          </div>
        ) : (
          <article className="provider-account">
            <div className="account-identity">
              {profile?.avatar ? <img src={profile.avatar} alt="" className="account-avatar-small" /> : null}
              <strong>{profile?.username || account.alias}</strong>
              <span>{t("acc.connected")}</span>
              <small>{account.last_synced_at ? `${t("acc.lastSync")} ${new Date(`${account.last_synced_at}Z`).toLocaleString()}` : t("acc.neverSync")}</small>
            </div>
            <div className="account-actions">
              <button className="danger" disabled={saving === account.id} onClick={() => void disconnect(account)}>{t("acc.disconnect")}</button>
            </div>
          </article>
        )}
      </div>
    );
  };

  return <section className="account-settings">
    <div className="account-heading">
      <div>
        <h2>{t("acc.title")}</h2>
        <p>{t("acc.d")}</p>
      </div>
    </div>

    {!onAccountTabChange && <div className="settings-tabs provider-subtabs">
      <button className={tab === "general" ? "active" : ""} onClick={() => setTab("general")}>{t("acc.general")}</button>
      {PROVIDERS.map((p) => (
        <button key={p.id} className={tab === p.id ? "active" : ""} onClick={() => setTab(p.id)}>{p.label}</button>
      ))}
    </div>}

    {error && <div className="modal-error">{error}</div>}
    {message && <div className="modal-success">{message}</div>}

    {tab === "general" && <div className="provider-general">
      <label className="primary-provider-field">
        <span>{t("acc.primary")}</span>
        <select
          value={authedProviders.length ? primaryProvider : ""}
          disabled={authedProviders.length === 0 || saving !== null}
          onChange={(e) => selectPrimary(e.target.value)}
        >
          {authedProviders.length === 0 && <option value="">{t("acc.none")}</option>}
          {authedProviders.map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}
        </select>
      </label>
      {generalExtras}
    </div>}

    {PROVIDERS.map((p) => (tab === p.id ? <div key={p.id} className="provider-tab-content">{renderProviderPanel(p.id)}{providerExtras?.(p.id)}</div> : null))}
  </section>;
}
