// Tooltip propio que reemplaza el nativo del sistema (que no es estilizable).
// Delegado: lee el atributo `title` de cualquier elemento, lo suprime para que no
// aparezca el del SO, y muestra uno estilizado. Cubre todos los `title=` sin tocarlos.

const SHOW_DELAY = 350;

export function installTooltips(): void {
  if (typeof document === "undefined" || document.getElementById("app-tooltip")) return;

  const tip = document.createElement("div");
  tip.id = "app-tooltip";
  tip.className = "app-tooltip";
  tip.setAttribute("role", "tooltip");
  document.body.appendChild(tip);

  let anchor: HTMLElement | null = null;
  let timer: number | undefined;

  const restore = () => {
    window.clearTimeout(timer);
    if (anchor) {
      const cached = anchor.getAttribute("data-title-cache");
      if (cached !== null) {
        anchor.setAttribute("title", cached);
        anchor.removeAttribute("data-title-cache");
      }
    }
    anchor = null;
    tip.classList.remove("visible");
  };

  const place = (el: HTMLElement) => {
    const r = el.getBoundingClientRect();
    const tr = tip.getBoundingClientRect();
    const left = Math.max(6, Math.min(r.left + r.width / 2 - tr.width / 2, window.innerWidth - tr.width - 6));
    let top = r.bottom + 7;
    if (top + tr.height > window.innerHeight - 6) top = r.top - tr.height - 7; // voltear arriba si no cabe
    tip.style.left = `${Math.round(left)}px`;
    tip.style.top = `${Math.round(Math.max(6, top))}px`;
  };

  document.addEventListener("mouseover", (event) => {
    const el = (event.target as HTMLElement)?.closest?.("[title]") as HTMLElement | null;
    if (!el || el === anchor) return;
    const text = el.getAttribute("title");
    if (!text) return;
    restore();
    anchor = el;
    el.setAttribute("data-title-cache", text);
    el.removeAttribute("title"); // suprime el tooltip nativo del SO
    timer = window.setTimeout(() => {
      if (anchor !== el) return;
      tip.textContent = text;
      tip.classList.add("visible");
      place(el);
    }, SHOW_DELAY);
  });

  document.addEventListener("mouseout", (event) => {
    if (!anchor) return;
    const to = event.relatedTarget as Node | null;
    if (to && anchor.contains(to)) return; // sigue dentro del mismo elemento
    restore();
  });

  // Evita tooltips atascados al desplazar, hacer clic o teclear.
  window.addEventListener("scroll", restore, true);
  document.addEventListener("mousedown", restore, true);
  document.addEventListener("keydown", restore, true);
  window.addEventListener("blur", restore);
}
