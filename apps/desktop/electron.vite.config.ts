import { defineConfig } from "electron-vite";
import react from "@vitejs/plugin-react";
import type { Plugin } from "vite";

const CSP_PRODUCCION = [
  // Sin un defecto cerrado, cualquier tipo de recurso omitido queda abierto.
  "default-src 'self'",
  // 127.0.0.1 sirve reader/assets; https conserva todas las portadas del proveedor;
  // blob permite imagenes generadas y data mantiene vivo el favicon del index.html.
  "img-src 'self' http://127.0.0.1:* https: blob: data:",
  // HTTP habla con la API local y WS sostiene playbackSocket; sin el ultimo la
  // deteccion de reproduccion queda muda aunque el resto de la app parezca sano.
  "connect-src 'self' http://127.0.0.1:* ws://127.0.0.1:*",
  // El renderer usa style={{...}} por todo el arbol; bloquearlo desarma la interfaz.
  "style-src 'self' 'unsafe-inline'",
  // En produccion solo se ejecutan los modulos construidos junto a index.html.
  "script-src 'self'",
  // Plugins, frames, cambios de base y envios de formulario no pertenecen al renderer.
  "object-src 'none'",
  "frame-src 'none'",
  "base-uri 'none'",
  "form-action 'none'",
].join("; ");

const CSP_DESARROLLO = [
  "default-src 'self'",
  "img-src 'self' http://127.0.0.1:* https: blob: data:",
  // El servidor de Vite y su WebSocket de HMR viven en el puerto load-bearing 1420.
  "connect-src 'self' http://127.0.0.1:* ws://127.0.0.1:* http://localhost:1420 ws://localhost:1420",
  "style-src 'self' 'unsafe-inline'",
  // Vite inyecta inline el preambulo de React Refresh. Esta concesion existe solo
  // durante `serve`; escribirla en index.html terminaria filtrandola a produccion.
  "script-src 'self' 'unsafe-inline'",
  "object-src 'none'",
  "frame-src 'none'",
  "base-uri 'none'",
  "form-action 'none'",
].join("; ");

function cspPlugin(): Plugin {
  let desarrollo = false;
  return {
    name: "nyanko-csp",
    configResolved(config) {
      desarrollo = config.command === "serve";
    },
    transformIndexHtml: {
      order: "pre",
      handler(html) {
        if (!html.includes("%CSP%")) throw new Error("Falta el marcador %CSP% en index.html");
        return html.replaceAll("%CSP%", desarrollo ? CSP_DESARROLLO : CSP_PRODUCCION);
      },
    },
  };
}

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
    plugins: [react(), cspPlugin()],
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
