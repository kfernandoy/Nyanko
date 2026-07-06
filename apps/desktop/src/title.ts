import type { TitleLanguage } from "./i18n";

type Titled = {
  title: string;
  title_romaji?: string | null;
  title_english?: string | null;
  title_native?: string | null;
};

// Idioma de títulos global (ajuste local): elige la variante pedida y cae al título
// preferido del proveedor si esa variante no existe. Aplica a todos los proveedores.
export function displayTitle(item: Titled, language: TitleLanguage): string {
  const variant = language === "ROMAJI" ? item.title_romaji
    : language === "ENGLISH" ? item.title_english
    : item.title_native;
  return variant || item.title;
}

// Forma de comparación insensible a símbolos: "fate stay night" debe encontrar
// "Fate/stay night" (los nombres de archivo de Windows no admiten / \ : * ?).
export function foldTitle(value: string): string {
  return value.toLocaleLowerCase().replace(/[^\p{L}\p{N}]+/gu, " ").trim();
}
