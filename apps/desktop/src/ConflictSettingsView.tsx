import { useEffect, useState } from "react";
import { api } from "./api";
import type { ConflictInfo, ConflictResolution } from "./types";

const FIELD_LABELS: Record<string, string> = {
  status: "Estado",
  progress: "Progreso",
};

export function ConflictSettingsView() {
  const [conflicts, setConflicts] = useState<ConflictInfo[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [manualValues, setManualValues] = useState<Record<number, string>>({});

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      setConflicts(await api.conflicts("pending"));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "No se pudieron cargar los conflictos");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const resolve = async (conflict: ConflictInfo, resolution: ConflictResolution) => {
    setError(null);
    try {
      await api.resolveConflict(conflict.id, resolution);
      setConflicts((current) => current.filter((item) => item.id !== conflict.id));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "No se pudo resolver el conflicto");
    }
  };

  const dismiss = async (conflict: ConflictInfo) => {
    setError(null);
    try {
      await api.dismissConflict(conflict.id);
      setConflicts((current) => current.filter((item) => item.id !== conflict.id));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "No se pudo descartar el conflicto");
    }
  };

  return (
    <div className="profile-settings">
      <div className="profile-heading">
        <div>
          <h2>Conflictos de sincronización</h2>
          <span>Cuando un proveedor cambia mientras Nyanko también tenía cambios locales</span>
        </div>
      </div>
      {loading ? (
        <p className="correction-empty">Cargando…</p>
      ) : conflicts.length === 0 ? (
        <p className="correction-empty">No hay conflictos pendientes.</p>
      ) : (
        <div className="conflict-list">
          {conflicts.map((conflict) => (
            <div key={conflict.id} className="conflict-card">
              <div className="conflict-header">
                <strong>{conflict.title}</strong>
                <small>{conflict.provider} · {conflict.alias} · {FIELD_LABELS[conflict.field] ?? conflict.field}</small>
              </div>
              <div className="conflict-values">
                <div>
                  <small>Local</small>
                  <span>{conflict.local_value ?? "—"}</span>
                </div>
                <div>
                  <small>Remoto</small>
                  <span>{conflict.remote_value ?? "—"}</span>
                </div>
              </div>
              <div className="conflict-actions">
                <button onClick={() => void resolve(conflict, { resolution: "local" })}>Usar local</button>
                <button onClick={() => void resolve(conflict, { resolution: "remote" })}>Usar remoto</button>
                <div className="conflict-manual">
                  <input
                    type="text"
                    placeholder="Valor manual"
                    value={manualValues[conflict.id] ?? ""}
                    onChange={(event) => setManualValues({ ...manualValues, [conflict.id]: event.target.value })}
                  />
                  <button
                    onClick={() =>
                      void resolve(conflict, {
                        resolution: "manual",
                        value: manualValues[conflict.id],
                      })
                    }
                    disabled={!manualValues[conflict.id]}
                  >
                    Usar manual
                  </button>
                </div>
                <button className="danger" onClick={() => void dismiss(conflict)}>Descartar</button>
              </div>
            </div>
          ))}
        </div>
      )}
      {error && <div className="modal-error">{error}</div>}
    </div>
  );
}
