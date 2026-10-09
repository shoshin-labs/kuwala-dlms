import { useContext } from "react";
import { LocaleContext, LocalePack } from "./i18n";
import english from "./locales/library-transfer.en.json";

const resources = require.context("./locales", false, /library-transfer\.[a-z]+\.json$/);
const packs: LocalePack[] = resources.keys().map(resources).filter((pack: LocalePack) => pack.code && pack.reviewed && pack.strings);
export function useLibraryTransferStrings() {
  const locale = useContext(LocaleContext);
  const pack = packs.find(item => item.code === locale) || english;
  return { ...english.strings, ...pack.strings };
}
