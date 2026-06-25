import { useCallback, useEffect, useMemo, useState } from "react";

import { api } from "./api";
import type { AssociationCandidateInfo, LinkedIdentityInfo } from "./types";

function message(reason: unknown): string {
  return reason instanceof Error ? reason.message : "No se pudo actualizar la asociación";
}

export function AssociationSettingsView() {
  const [candidates, setCandidates] = useState<AssociationCandidateInfo[]>([]);
  const [identities, setIdentities] = useState<LinkedIdentityInfo[]>([]);
  const [saving, setSaving] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    const [pending, linked] = await Promise.all([
      api.associationCandidates(),
      api.linkedIdentities(),
    ]);
    setCandidates(pending);
    setIdentities(linked);
  }, []);

  useEffect(() => { void load().catch((reason) => setError(message(reason))); }, [load]);

  const groups = useMemo(() => {
    const grouped = new Map<number, LinkedIdentityInfo[]>();
    for (const identity of identities) {
      grouped.set(identity.media_id, [...(grouped.get(identity.media_id) ?? []), identity]);
    }
    return grouped;
  }, [identities]);

  const resolve = async (candidate: AssociationCandidateInfo) => {
    if (!window.confirm(`¿Asociar “${candidate.source_title}” con “${candidate.candidate_title}”?`)) return;
    setSaving(candidate.id);
    setError(null);
    try {
      await api.resolveAssociation(candidate.id);
      await load();
    } catch (reason) {
      setError(message(reason));
    } finally {
      setSaving(null);
    }
  };

  const dismiss = async (candidate: AssociationCandidateInfo) => {
    setSaving(candidate.id);
    setError(null);
    try {
      await api.dismissAssociation(candidate.id);
      await load();
    } catch (reason) {
      setError(message(reason));
    } finally {
      setSaving(null);
    }
  };

  const separate = async (identity: LinkedIdentityInfo) => {
    if (!window.confirm(`¿Separar ${identity.provider}:${identity.external_id} de “${identity.title}”? El historial se conservará.`)) return;
    setSaving(-identity.identity_id);
    setError(null);
    try {
      await api.separateIdentity(identity.identity_id);
      await load();
    } catch (reason) {
      setError(message(reason));
    } finally {
      setSaving(null);
    }
  };

  return <section className="association-settings">
    <div><h2>Asociaciones entre catálogos</h2><p>Nyanko no fusiona coincidencias ambiguas sin confirmación.</p></div>
    {error && <div className="modal-error">{error}</div>}
    {candidates.length > 0 && <div className="association-candidates">
      <h3>Pendientes ({candidates.length})</h3>
      {candidates.map((candidate) => <article key={candidate.id}>
        <div><strong>{candidate.source_title}</strong><span>{candidate.source_provider}:{candidate.source_external_id}</span></div>
        <span className="association-arrow">→</span>
        <div><strong>{candidate.candidate_title}</strong><span>Confianza {(candidate.confidence * 100).toFixed(0)}%</span></div>
        <div className="association-actions"><button disabled={saving === candidate.id} onClick={() => void dismiss(candidate)}>Mantener separadas</button><button className="primary" disabled={saving === candidate.id} onClick={() => void resolve(candidate)}>Asociar</button></div>
      </article>)}
    </div>}
    <details className="linked-identities"><summary>Asociaciones actuales ({groups.size})</summary>
      {[...groups.entries()].map(([mediaId, linked]) => <article key={mediaId}>
        <strong>{linked[0]?.title}</strong>
        <div>{linked.map((identity) => <span key={identity.identity_id}>{identity.provider}:{identity.external_id}<button disabled={saving === -identity.identity_id} onClick={() => void separate(identity)}>Separar</button></span>)}</div>
      </article>)}
      {!groups.size && <p>No hay obras enlazadas entre proveedores.</p>}
    </details>
  </section>;
}
