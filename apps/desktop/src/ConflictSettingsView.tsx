import { useEffect, useState } from "react";
import { api } from "./api";
import { useApp } from "./i18n";
import type { ConflictInfo, ConflictResolution } from "./types";

export function ConflictSettingsView() {
  const { t } = useApp();
  const [conflicts, setConflicts] = useState<ConflictInfo[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [manualValues, setManualValues] = useState<Record<number, string>>({});

  const fieldLabels: Record<string, string> = {
    status: t("conf.field.status"),
    progress: t("conf.field.progress"),
  };

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      setConflicts(await api.conflicts("pending"));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : t("conf.loadError"));
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
      setError(reason instanceof Error ? reason.message : t("conf.resolveError"));
    }
  };

  const dismiss = async (conflict: ConflictInfo) => {
    setError(null);
    try {
      await api.dismissConflict(conflict.id);
      setConflicts((current) => current.filter((item) => item.id !== conflict.id));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : t("conf.dismissError"));
    }
  };

  return (
    <div className="profile-settings">
      <div className="profile-heading">
        <div>
          <h2>{t("conf.title")}</h2>
          <span>{t("conf.d")}</span>
        </div>
      </div>
      {loading ? (
        <p className="correction-empty">{t("common.loading")}</p>
      ) : conflicts.length === 0 ? (
        <p className="correction-empty">{t("conf.empty")}</p>
      ) : (
        <div className="conflict-list">
          {conflicts.map((conflict) => (
            <div key={conflict.id} className="conflict-card">
              <div className="conflict-header">
                <strong>{conflict.title}</strong>
                <small>{conflict.provider} · {conflict.alias} · {fieldLabels[conflict.field] ?? conflict.field}</small>
              </div>
              <div className="conflict-values">
                <div>
                  <small>{t("conf.local")}</small>
                  <span>{conflict.local_value ?? "—"}</span>
                </div>
                <div>
                  <small>{t("conf.remote")}</small>
                  <span>{conflict.remote_value ?? "—"}</span>
                </div>
              </div>
              <div className="conflict-actions">
                <button onClick={() => void resolve(conflict, { resolution: "local" })}>{t("conf.useLocal")}</button>
                <button onClick={() => void resolve(conflict, { resolution: "remote" })}>{t("conf.useRemote")}</button>
                <div className="conflict-manual">
                  <input
                    type="text"
                    placeholder={t("conf.manualValue")}
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
                    {t("conf.useManual")}
                  </button>
                </div>
                <button className="danger" onClick={() => void dismiss(conflict)}>{t("conf.dismiss")}</button>
              </div>
            </div>
          ))}
        </div>
      )}
      {error && <div className="modal-error">{error}</div>}
    </div>
  );
}
