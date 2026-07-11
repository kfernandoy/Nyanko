import { native } from "./native";

// El tipo vive ahora en native.ts; se re-exporta para no tocar los call sites de
// DetectorSettingsView.
export type { WindowPrefs } from "./native";
import type { WindowPrefs } from "./native";

// native.getWindowPrefs/setWindowPrefs son stubs de Fase 4 (NATIVE-04).
export const getWindowPrefs = (): Promise<WindowPrefs> => native.getWindowPrefs();
export const setWindowPrefs = (prefs: WindowPrefs): Promise<void> => native.setWindowPrefs(prefs);
