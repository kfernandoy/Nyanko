/// <reference types="vite/client" />

// Bridge nativo expuesto por electron/preload/index.ts (contextBridge).
// Opcional: en dev/degradado la app puede correr sin él.
interface Window {
  nyanko?: {
    openLogsFolder: () => Promise<string>;
    retryStartup: () => Promise<void>;
    quit: () => void;
    readAppDataFile: (name: string) => Promise<string | null>;
    appVersion: () => Promise<string>;
    openExternal: (url: string) => Promise<void>;
    openPath: (path: string) => Promise<string>;
    revealItemInDir: (path: string) => Promise<void>;
    openFolderDialog: () => Promise<string | null>;
    notify: (title: string, body: string) => Promise<void>;
    onDetectionPaused: (cb: (paused: boolean) => void) => () => void;
    minimizeWindow: () => Promise<void>;
    toggleMaximizeWindow: () => Promise<void>;
    closeWindow: () => Promise<void>;
    getWindowPrefs: () => Promise<{
      close_to_tray: boolean;
      minimize_to_tray: boolean;
      start_minimized: boolean;
    }>;
    setWindowPrefs: (prefs: {
      close_to_tray: boolean;
      minimize_to_tray: boolean;
      start_minimized: boolean;
    }) => Promise<void>;
    setDiscordActivity: (payload: {
      details: string;
      state: string;
      start_timestamp?: number;
    }) => Promise<void>;
    clearDiscordActivity: () => Promise<void>;
    getAutostart: () => Promise<boolean>;
    setAutostart: (enabled: boolean) => Promise<void>;
    checkForUpdates: () => Promise<{ version: string } | null>;
    installUpdate: () => Promise<void>;
  };
}
