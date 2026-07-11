// Frontera nativa ÚNICA (NATIVE-01): el único módulo que el renderer importa para
// ops nativas. Cada op enruta por window.nyanko (contextBridge) → ipcMain.handle.
// Las ops de Fase 4/5 son stubs marcados para que ningún import de Tauri deba
// sobrevivir. Regla dura: TODO acceso a `window` vive dentro de cuerpos de función
// (nunca al top level) para que native.ts sea importable bajo `node --import tsx` en
// el self-check sin DOM.

// windowPrefs.ts y discord.ts se reducen a re-exports en 03-02: native.ts pasa a
// ser el hogar de estos tipos.
export type WindowPrefs = {
  close_to_tray: boolean;
  minimize_to_tray: boolean;
  start_minimized: boolean;
};

export type DiscordActivity = {
  details: string;
  state: string;
  start_timestamp?: number;
};

// True cuando el bridge de Electron está presente (prod/dev empaquetado).
export const isNative = typeof window !== "undefined" && !!window.nyanko;

export const native = {
  // ── Ops cableadas (equivalente Electron ya existe) ──
  openExternal(url: string): Promise<void> {
    // Fallback web (dev sin bridge): mismo comportamiento que el viejo App.tsx.
    if (window.nyanko) return window.nyanko.openExternal(url);
    window.open(url, "_blank", "noopener,noreferrer");
    return Promise.resolve();
  },
  openPath(path: string): Promise<string> {
    return window.nyanko?.openPath(path) ?? Promise.resolve("");
  },
  revealItemInDir(path: string): Promise<void> {
    return window.nyanko?.revealItemInDir(path) ?? Promise.resolve();
  },
  openFolderDialog(): Promise<string | null> {
    return window.nyanko?.openFolderDialog() ?? Promise.resolve(null);
  },
  appVersion(): Promise<string> {
    return window.nyanko?.appVersion() ?? Promise.resolve("");
  },
  notify(title: string, body: string): Promise<void> {
    return window.nyanko?.notify(title, body) ?? Promise.resolve();
  },
  onDetectionPaused(cb: (paused: boolean) => void): () => void {
    return window.nyanko ? window.nyanko.onDetectionPaused(cb) : () => {};
  },
  readAppDataFile(name: string): Promise<string | null> {
    return window.nyanko?.readAppDataFile(name) ?? Promise.resolve(null);
  },

  // ── Stubs Fase 4 (no-op seguro) ──
  getAutostart(): Promise<boolean> {
    // ponytail: autostart llega en Fase 4 (NATIVE-06)
    return Promise.resolve(false);
  },
  setAutostart(_enabled: boolean): Promise<void> {
    // ponytail: autostart llega en Fase 4 (NATIVE-06)
    return Promise.resolve();
  },
  getWindowPrefs(): Promise<WindowPrefs> {
    // Fallback web (dev sin bridge): defaults; en Electron lee window_prefs.json.
    return (
      window.nyanko?.getWindowPrefs() ??
      Promise.resolve({
        close_to_tray: false,
        minimize_to_tray: false,
        start_minimized: false,
      })
    );
  },
  setWindowPrefs(prefs: WindowPrefs): Promise<void> {
    return window.nyanko?.setWindowPrefs(prefs) ?? Promise.resolve();
  },
  setDiscordActivity(_payload: DiscordActivity): Promise<void> {
    // ponytail: Discord RPC en Fase 4 (NATIVE-05) — silencioso, como el viejo ignore-on-error
    return Promise.resolve();
  },
  clearDiscordActivity(): Promise<void> {
    // ponytail: Discord RPC en Fase 4 (NATIVE-05)
    return Promise.resolve();
  },

  // ── Controles de ventana (NATIVE-04) — op cableada con fallback web no-op ──
  minimizeWindow(): Promise<void> {
    return window.nyanko?.minimizeWindow() ?? Promise.resolve();
  },
  toggleMaximizeWindow(): Promise<void> {
    return window.nyanko?.toggleMaximizeWindow() ?? Promise.resolve();
  },
  closeWindow(): Promise<void> {
    return window.nyanko?.closeWindow() ?? Promise.resolve();
  },

  // ── Stub Fase 5 (throw) ──
  checkForUpdates(): Promise<void> {
    // ponytail: actualizador en Fase 5 (PKG-02)
    throw new Error("Actualizaciones: Fase 5");
  },
};

// Manifest: toda clave-op de función arriba (cableadas + stubs). El self-check
// (native.test.ts) lo compara contra `native` en ambas direcciones. NO incluye
// isNative (es boolean, no una op).
export const NATIVE_OPS: string[] = [
  "openExternal",
  "openPath",
  "revealItemInDir",
  "openFolderDialog",
  "appVersion",
  "notify",
  "onDetectionPaused",
  "readAppDataFile",
  "getAutostart",
  "setAutostart",
  "getWindowPrefs",
  "setWindowPrefs",
  "setDiscordActivity",
  "clearDiscordActivity",
  "minimizeWindow",
  "toggleMaximizeWindow",
  "closeWindow",
  "checkForUpdates",
];
