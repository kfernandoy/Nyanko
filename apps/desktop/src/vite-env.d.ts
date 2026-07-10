/// <reference types="vite/client" />

// Bridge nativo expuesto por electron/preload/index.ts (contextBridge).
// Opcional: en dev/degradado la app puede correr sin él.
interface Window {
  nyanko?: {
    appVersion: string;
    openLogsFolder: () => Promise<string>;
    retryStartup: () => Promise<void>;
    quit: () => void;
  };
}
