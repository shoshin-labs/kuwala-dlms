import { useContext } from 'react';
import { LocaleContext, LocalePack } from './i18n';
import english from './locales/manager.en.json';

const resources = require.context('./locales', false, /manager\.[a-z]+\.json$/);
const packs: LocalePack[] = resources.keys().map(resources).filter((pack: LocalePack) => pack.code && pack.reviewed && pack.strings);
export function useManagerStrings() {
  const locale = useContext(LocaleContext); const pack = packs.find(item => item.code === locale) || english;
  return (key: keyof typeof english.strings, values: Record<string, string | number> = {}) =>
    (pack.strings[key] || english.strings[key]).replace(/\{(\w+)\}/g, (match, key) => values[key] === undefined ? match : String(values[key]));
}
