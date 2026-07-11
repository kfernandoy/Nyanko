import { native } from "./native";

// El tipo vive ahora en native.ts; se re-exporta para no tocar los call sites de App.tsx.
export type { DiscordActivity } from "./native";
import type { DiscordActivity } from "./native";

// native.setDiscordActivity/clearDiscordActivity son stubs de Fase 4 (NATIVE-05).
export const setDiscordActivity = (payload: DiscordActivity): Promise<void> =>
  native.setDiscordActivity(payload);
export const clearDiscordActivity = (): Promise<void> => native.clearDiscordActivity();
