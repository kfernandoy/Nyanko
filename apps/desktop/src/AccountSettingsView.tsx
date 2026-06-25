import { useCallback, useEffect, useState } from "react";

import { api } from "./api";
import type { AccountInfo } from "./types";

function accountError(reason: unknown): string {
  return reason instanceof Error ? reason.message : "No se pudo actualizar la cuenta";
}

export function AccountSettingsView({
  onConnect,
  onAccountChanged,
}: {
  onConnect: (provider: string, alias: string) => Promise<void>;
  onAccountChanged: (provider: string, alias: string) => Promise<void>;
}) {
  const [accounts, setAccounts] = useState<AccountInfo[]>([]);
  const [alias, setAlias] = useState("");
  const [provider, setProvider] = useState("anilist");
  const [saving, setSaving] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const load = useCallback(async () => {
    setAccounts(await api.accounts());
  }, []);

  useEffect(() => {
    void load().catch((reason) => setError(accountError(reason)));
    const refresh = () => void load().catch(() => {});
    window.addEventListener("focus", refresh);
    return () => window.removeEventListener("focus", refresh);
  }, [load]);

  const update = async (
    account: AccountInfo,
    change: Partial<Pick<AccountInfo, "sync_direction" | "is_primary">>,
  ) => {
    setSaving(account.id);
    setError(null);
    setMessage(null);
    try {
      await api.updateAccount(account.id, change);
      await load();
      if (change.is_primary) await onAccountChanged(account.provider, account.alias);
    } catch (reason) {
      setError(accountError(reason));
    } finally {
      setSaving(null);
    }
  };

  const connect = async () => {
    const nextAlias = alias.trim();
    if (!/^[a-zA-Z0-9_-]{1,32}$/.test(nextAlias)) {
      setError("El alias debe tener entre 1 y 32 caracteres: letras, números, _ o -.");
      return;
    }
    setError(null);
    await onConnect(provider, nextAlias);
    setAlias("");
  };

  const disconnect = async (account: AccountInfo) => {
    if (!window.confirm(`¿Desconectar la cuenta ${account.alias} de ${account.provider}?`)) return;
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

  const importMal = async (account: AccountInfo) => {
    setSaving(account.id);
    setError(null);
    setMessage(null);
    try {
      const result = await api.importMal(account.alias);
      await load();
      setMessage(`${result.imported} entradas importadas desde MyAnimeList.`);
    } catch (reason) {
      setError(accountError(reason));
    } finally {
      setSaving(null);
    }
  };

  return <section className="account-settings">
    <div className="account-heading">
      <div>
        <h2>Cuentas y proveedores</h2>
        <p>La cuenta principal alimenta la biblioteca local. Las demás conservan su copia remota separada.</p>
      </div>
      <div className="account-connect">
        <select aria-label="Proveedor" value={provider} onChange={(event) => setProvider(event.target.value)}><option value="anilist">AniList</option><option value="mal">MyAnimeList</option></select>
        <input value={alias} maxLength={32} placeholder="Alias de cuenta" aria-label="Alias de cuenta" onChange={(event) => setAlias(event.target.value)} />
        <button className="primary" disabled={!alias.trim()} onClick={() => void connect()}>Conectar</button>
      </div>
    </div>
    {error && <div className="modal-error">{error}</div>}
    {message && <div className="modal-success">{message}</div>}
    <div className="account-list">
      {accounts.map((account) => <article key={account.id}>
        <div className="account-identity">
          <strong>{account.alias}</strong>
          <span>{account.provider} · {account.authenticated ? "conectada" : "sin autenticar"}</span>
          <small>{account.last_synced_at ? `Última sincronización: ${new Date(`${account.last_synced_at}Z`).toLocaleString("es")}` : "Aún no sincronizada"}</small>
        </div>
        <label>Dirección
          <select disabled={saving === account.id || account.provider === "mal"} value={account.sync_direction} onChange={(event) => void update(account, { sync_direction: event.target.value as AccountInfo["sync_direction"] })}>
            <option value="import">Sólo importar</option>
            <option value="bidirectional">Bidireccional</option>
            <option value="export">Sólo exportar</option>
          </select>
        </label>
        <label className="primary-account"><input type="radio" name={`primary-account-${account.provider}`} checked={account.is_primary} disabled={saving === account.id} onChange={() => void update(account, { is_primary: true })} /> Principal</label>
        <div className="account-actions">{account.authenticated
          ? <>{account.provider === "mal" && <button className="primary" disabled={saving === account.id} onClick={() => void importMal(account)}>Importar</button>}<button className="danger" disabled={saving === account.id} onClick={() => void disconnect(account)}>Desconectar</button></>
          : <button disabled={saving === account.id} onClick={() => void onConnect(account.provider, account.alias)}>Reconectar</button>}</div>
      </article>)}
      {!accounts.length && <p className="account-empty">No hay cuentas registradas.</p>}
    </div>
  </section>;
}
