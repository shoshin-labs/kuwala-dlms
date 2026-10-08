import React, { createContext, useContext } from "react";
import english from "./locales/en.json";

export interface LocalePack {
  code: string;
  name: string;
  nativeName: string;
  reviewed: boolean;
  strings: Record<string, string>;
}
// Webpack includes each pack in the offline bundle. Offer reviewed packs only.
const resources = require.context("./locales", false, /\.json$/);
export const locales: LocalePack[] = resources
  .keys()
  .map(resources)
  .filter((pack: LocalePack) => pack.code && pack.reviewed && pack.strings)
  .sort((a: LocalePack, b: LocalePack) =>
    a.code === "en" ? -1 : b.code === "en" ? 1 : a.name.localeCompare(b.name),
  );
export const LocaleContext = createContext("en");
export function useStrings() {
  const code = useContext(LocaleContext);
  const pack = locales.find((locale) => locale.code === code) || english;
  return (
    key: keyof typeof english.strings,
    values: Record<string, string | number> = {},
  ) =>
    (pack.strings[key] || english.strings[key]).replace(
      /\{(\w+)\}/g,
      (match, name) =>
        values[name] === undefined ? match : String(values[name]),
    );
}
