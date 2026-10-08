# Manage Library language resources

`manager.en.json` contains the new private management interface copy. Its
`scope: "manager"` keeps it out of the visitor language selector. The manager
uses the existing `LocaleContext` and loads reviewed `manager.<code>.json` packs
locally through `manager_strings.tsx`, with an English fallback.

For Chichewa (`ny`), Swahili (`sw`), Zulu (`zu`) or French (`fr`), copy the pack,
translate every string, preserve placeholders, and retain `reviewed: false`
until a fluent reviewer checks the management and rights language. A matching
reviewed visitor pack makes that language available in the shared selector.
Rebuild to bundle both packs; no remote fonts, CDN or translation service is used.

Document titles, library names and metadata field/value names are catalogue
data. The editor preserves their IDs and text instead of translating or replacing
them. Existing advanced tools still contain legacy English interface copy.
