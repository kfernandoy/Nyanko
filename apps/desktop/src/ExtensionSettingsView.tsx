import { useCallback, useEffect, useState } from "react";

import { api } from "./api";
import type { ExtensionClientInfo } from "./types";

function formatDate(timestamp: number | null): string {
  return timestamp ? new Date(timestamp * 1000).toLocaleString("es") : "Nunca";
}

export function ExtensionSettingsView() {
  const [clients, setClients] = useState<ExtensionClientInfo[]>([]);
  const [pairing, setPairing] = useState<{ code: string; expires_at: number; api_url: string } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setClients(await api.extensionClients());
  }, []);

  useEffect(() => { void load().catch(() => {}); }, [load]);

  const startPairing = async () => {
    setError(null);
    try {
      setPairing(await api.startExtensionPairing());
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "No se pudo iniciar el emparejamiento");
    }
  };

  const revoke = async (client: ExtensionClientInfo) => {
    if (!window.confirm(`¿Revocar el acceso de ${client.label}?`)) return;
    try {
      await api.revokeExtensionClient(client.id);
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "No se pudo revocar la extensión");
    }
  };

  return <section className="extension-settings">
    <div className="extension-heading"><div><h2>Extensión del navegador</h2><p>Empareja Chromium o Firefox mediante un código temporal. Cada instalación recibe un token independiente.</p></div><button className="primary" onClick={() => void startPairing()}>Generar código</button></div>
    {pairing && <div className="pairing-code"><strong>{pairing.code}</strong><span>Servicio: {pairing.api_url}<br />Válido hasta {formatDate(pairing.expires_at)}. Introduce ambos datos en las opciones de la extensión.</span></div>}
    {error && <div className="modal-error">{error}</div>}
    <div className="extension-clients">{clients.filter((client) => !client.revoked_at).map((client) => <article key={client.id}><div><strong>{client.label}</strong><span>Último evento: {formatDate(client.last_seen_at)} · vence {formatDate(client.expires_at)}</span></div><button className="danger" onClick={() => void revoke(client)}>Revocar</button></article>)}{!clients.some((client) => !client.revoked_at) && <p>No hay extensiones emparejadas.</p>}</div>
  </section>;
}
