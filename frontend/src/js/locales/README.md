# Interface language resources

The visitor shell, catalogue, document detail and About use `en.json`, following
the locale-pack shape used in Oasis. The original DLMS frontend had no localisation
framework. Webpack bundles JSON resources through `i18n.tsx`; language changes
require no CDN or translation service.

To add Chichewa (`ny`), Swahili (`sw`), Zulu (`zu`) or French (`fr`):

1. Copy `en.json` to `<code>.json`, retaining every string key and `{placeholder}`.
2. Set `code`, `name`, `nativeName` and translated `strings`. Keep `reviewed: false`
   until reviewed by speakers familiar with this community/library context.
3. Set `reviewed: true` after review and rebuild. Reviewed packs automatically
   appear in the selector; missing keys fall back to English.
4. Check phone layouts, long text, focus and original-link labels in that language.

Only English is included now. No untranslated pack is presented as a supported
language. The software licence retains its original legal text. Titles, folders
and metadata are authoring data, not interface strings.

`curator.en.json` holds new private curator navigation/home/detail copy; it is not
a visitor locale pack. Remaining curator forms/validation text is legacy English.
Moving it into resources and integrating curator locale selection is a follow-up.
Put all new interface copy in resources.
