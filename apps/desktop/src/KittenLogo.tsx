// Logo de Nyanko: carita de gato en el morado de marca (currentColor), con parpadeo
// sutil y un guiño al pasar el mouse. Reemplaza el kanji 猫. Escala con el tamaño dado.
export function KittenLogo({ className = "" }: { className?: string }) {
  return (
    <svg
      className={`kitten-logo ${className}`}
      viewBox="0 0 40 40"
      role="img"
      aria-label="Nyanko"
    >
      <g fill="currentColor">
        {/* orejas */}
        <path className="kitten-ear kitten-ear-l" d="M8 18 L9 4 L19 12 Z" />
        <path className="kitten-ear kitten-ear-r" d="M32 18 L31 4 L21 12 Z" />
        {/* cabeza */}
        <circle cx="20" cy="24" r="13" />
      </g>
      <g className="kitten-face">
        <ellipse className="kitten-eye" cx="15" cy="24" rx="2.2" ry="3" />
        <ellipse className="kitten-eye" cx="25" cy="24" rx="2.2" ry="3" />
        <path className="kitten-nose" d="M18.4 28 H21.6 L20 29.9 Z" />
      </g>
    </svg>
  );
}
