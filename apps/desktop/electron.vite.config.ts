import { defineConfig } from "electron-vite";
import react from "@vitejs/plugin-react";

// Config electron-vite: main + preload + renderer.
// El renderer reutiliza el index.html + src/ existentes sin cambios (root = este dir).
export default defineConfig({
  main: {
    build: {
      lib: { entry: "electron/main/index.ts" },
    },
  },
  preload: {
    build: {
      // sandbox:true exige preload CommonJS; con "type":"module" en package.json
      // electron-vite emitiría .mjs (ESM), que un renderer sandbox no carga.
      // Forzamos salida CJS con extensión .cjs.
      lib: { entry: "electron/preload/index.ts" },
      rollupOptions: {
        output: { format: "cjs", entryFileNames: "index.cjs" },
      },
    },
  },
  renderer: {
    // El index.html vive en la raíz del proyecto y referencia /src/main.tsx.
    root: ".",
    plugins: [react()],
    // Port 1420 es load-bearing: el CORS del backend (desktop_url) lo tiene fijado.
    envPrefix: ["VITE_", "TAURI_ENV_"],
    server: {
      port: 1420,
      strictPort: true,
    },
    build: {
      rollupOptions: {
        input: "index.html",
      },
    },
  },
});
