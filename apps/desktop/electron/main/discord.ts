import { Client } from "@xhayper/discord-rpc";
import type { SetActivity } from "@xhayper/discord-rpc";
import log from "electron-log";

// Discord Rich Presence (NATIVE-05). Paridad exacta con el viejo discord.rs (D-02/D-03):
// client id por defecto + override por env, conexión PEREZOSA (en el primer setActivity)
// y no-op SILENCIOSO si Discord no está corriendo o el id no está configurado.
// ponytail: sin bucle de reconexión ni backoff — conectar-perezoso + tragarse el error +
// soltar el cliente (para reconectar en la siguiente llamada) es TODO el contrato de 0.1.15.

const DEFAULT_CLIENT_ID = "1521045260342525962";
// Centinela del Rust original: si alguien deja este valor, RP queda como no-op.
const UNCONFIGURED = "REPLACE_WITH_YOUR_DISCORD_CLIENT_ID";

function clientId(): string {
  return process.env.NYANKO_DISCORD_CLIENT_ID || DEFAULT_CLIENT_ID;
}

// Slot a nivel de módulo (el análogo del Mutex<Option<DiscordIpcClient>> de Rust).
let client: Client | null = null;

// T-04-09: el id del cliente sale SOLO de env/const, nunca del renderer. El renderer
// aporta únicamente details/state/start_timestamp, que se coaccionan aquí.
export type DiscordActivityPayload = {
  details: string;
  state: string;
  start_timestamp?: number;
};

async function connected(): Promise<Client | null> {
  if (client) return client;
  const id = clientId();
  if (!id || id === UNCONFIGURED) return null;
  try {
    const c = new Client({ clientId: id });
    // El transporte IPC es un EventEmitter: un 'error' sin listener tumbaría el proceso
    // main cuando Discord se cierra a mitad de sesión. Lo tragamos (T-04-08).
    c.on("error", () => {});
    await c.login();
    client = c;
    return client;
  } catch {
    // Discord cerrado / socket ausente → no-op silencioso (D-03).
    client = null;
    return null;
  }
}

// Suelta el cliente para que la próxima llamada reconecte (paridad `*slot = None`).
function drop(): void {
  const c = client;
  client = null;
  void c?.destroy().catch(() => {});
}

export async function setDiscordActivity(payload: unknown): Promise<void> {
  const p = (payload ?? {}) as Partial<DiscordActivityPayload>;
  const details = typeof p.details === "string" ? p.details : "";
  const state = typeof p.state === "string" ? p.state : "";
  const start = typeof p.start_timestamp === "number" ? p.start_timestamp : undefined;

  const c = await connected();
  if (!c) return; // Discord no corre o id sin configurar → salir en silencio.

  // Solo se incluyen los campos con contenido: Discord rechaza details/state vacíos.
  const activity: SetActivity = {};
  if (details) activity.details = details;
  if (state) activity.state = state;
  if (start !== undefined) activity.startTimestamp = start;

  try {
    await c.user?.setActivity(activity);
  } catch (err) {
    // Discord probablemente se cerró: soltamos el cliente y reconectamos la próxima vez.
    log.debug("discord: setActivity falló, soltando cliente", err);
    drop();
  }
}

export async function clearDiscordActivity(): Promise<void> {
  if (!client) return;
  try {
    await client.user?.clearActivity();
  } catch {
    // Ignorar (paridad `let _ = client.clear_activity()`).
  }
}
