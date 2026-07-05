import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";

export type CtxItem =
  | { sep: true }
  | { label: string; onClick?: () => void; sub?: CtxItem[]; disabled?: boolean; danger?: boolean; checked?: boolean };

export function useContextMenu() {
  const [state, setState] = useState<{ x: number; y: number; items: CtxItem[] } | null>(null);
  const openMenu = useCallback((event: React.MouseEvent, items: CtxItem[]) => {
    event.preventDefault();
    event.stopPropagation();
    setState({ x: event.clientX, y: event.clientY, items });
  }, []);
  const menu = state
    ? <ContextMenuPanel x={state.x} y={state.y} items={state.items} onClose={() => setState(null)} />
    : null;
  return { openMenu, menu };
}

// Los constructores de menú usan spreads condicionales; aquí se colapsan los
// separadores sobrantes (iniciales, finales o consecutivos) que eso deja.
function cleanItems(items: CtxItem[]): CtxItem[] {
  const clean: CtxItem[] = [];
  for (const item of items) {
    if ("sep" in item && (clean.length === 0 || "sep" in clean[clean.length - 1])) continue;
    clean.push(item);
  }
  while (clean.length > 0 && "sep" in clean[clean.length - 1]) clean.pop();
  return clean;
}

// El wrap decide hacia dónde abre el submenú según el espacio disponible.
// ponytail: 210px ≈ ancho típico del submenú; medir el real exigiría montarlo antes del hover.
function SubMenu({ label, items, onClose }: { label: string; items: CtxItem[]; onClose: () => void }) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const [flip, setFlip] = useState(false);
  const [up, setUp] = useState(false);
  const onEnter = () => {
    const rect = wrapRef.current?.getBoundingClientRect();
    if (!rect) return;
    setFlip(rect.right + 210 > window.innerWidth);
    setUp(rect.top > window.innerHeight / 2);
  };
  return (
    <div ref={wrapRef} className="ctx-sub-wrap" onMouseEnter={onEnter}>
      <button type="button" className="ctx-item">
        {label}
        <span className="ctx-sub-arrow">▸</span>
      </button>
      <div className={`ctx-sub${flip ? " flip" : ""}${up ? " up" : ""}`}>
        <ItemList items={items} onClose={onClose} />
      </div>
    </div>
  );
}

function ItemList({ items, onClose }: { items: CtxItem[]; onClose: () => void }) {
  return <>
    {cleanItems(items).map((item, index) => {
      if ("sep" in item) return <div key={index} className="ctx-sep" />;
      if (item.sub) {
        return <SubMenu key={index} label={item.label} items={item.sub} onClose={onClose} />;
      }
      return (
        <button
          key={index}
          type="button"
          className={`ctx-item${item.danger ? " danger" : ""}`}
          disabled={item.disabled}
          onClick={() => { onClose(); item.onClick?.(); }}
        >
          {item.checked != null && <span className="ctx-check">{item.checked ? "✓" : ""}</span>}
          {item.label}
        </button>
      );
    })}
  </>;
}

function ContextMenuPanel({ x, y, items, onClose }: {
  x: number; y: number; items: CtxItem[]; onClose: () => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState({ x, y });

  // Mantener el menú dentro del viewport.
  useLayoutEffect(() => {
    const rect = ref.current?.getBoundingClientRect();
    if (!rect) return;
    setPos({
      x: Math.max(4, Math.min(x, window.innerWidth - rect.width - 4)),
      y: Math.max(4, Math.min(y, window.innerHeight - rect.height - 4)),
    });
  }, [x, y]);

  useEffect(() => {
    const onDown = (event: MouseEvent) => {
      if (!ref.current?.contains(event.target as Node)) onClose();
    };
    const onKey = (event: KeyboardEvent) => { if (event.key === "Escape") onClose(); };
    const close = () => onClose();
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    document.addEventListener("scroll", close, true);
    window.addEventListener("blur", close);
    window.addEventListener("resize", close);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("scroll", close, true);
      window.removeEventListener("blur", close);
      window.removeEventListener("resize", close);
    };
  }, [onClose]);

  return (
    <div ref={ref} className="ctx-menu" style={{ left: pos.x, top: pos.y }} onContextMenu={(e) => e.preventDefault()}>
      <ItemList items={items} onClose={onClose} />
    </div>
  );
}
