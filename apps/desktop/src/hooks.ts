import { useEffect, useState } from "react";

// Ventana estrecha: las vistas de biblioteca fuerzan el modo lista.
const COMPACT_QUERY = "(max-width: 760px)";

export function useCompact(): boolean {
  const [compact, setCompact] = useState(() => window.matchMedia(COMPACT_QUERY).matches);
  useEffect(() => {
    const media = window.matchMedia(COMPACT_QUERY);
    const onChange = (event: MediaQueryListEvent) => setCompact(event.matches);
    media.addEventListener("change", onChange);
    return () => media.removeEventListener("change", onChange);
  }, []);
  return compact;
}
