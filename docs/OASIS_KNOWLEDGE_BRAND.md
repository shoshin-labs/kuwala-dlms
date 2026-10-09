# Oasis Knowledge brand

Oasis Knowledge is the collection and its curator workspace. It contains named
**libraries**, and each library contains **sections** and original documents.
Sections may contain further sections. Oasis remains the conversational interface.

## Palette

| Colour | Hex | Role |
|---|---|---|
| Graphite | `#343330` | Main text, amber button text |
| Dark Khaki | `#45462A` | Wordmark, dark controls and navigation |
| Olive Bark | `#7E5920` | Links, focus outlines and control borders |
| Amber Earth | `#DC851F` | Primary action hover |
| Amber Glow | `#FFA737` | Primary action background |

Keep the working surface white with light warm neutral separators. Use graphite
text on either amber. White text is reserved for sufficiently dark graphite,
khaki, olive or existing semantic error controls; never white on amber. Body text,
links, labels and actions retain high contrast. Colour supplements labels rather
than being the only signal for selected libraries, failed jobs or stale indexes.

The reusable palette tokens are in `frontend/src/css/style.css`. Material UI's
matching theme is in `frontend/src/js/oasis_app.tsx`. The existing semantic error
red is retained for failure/destructive actions. Original document artwork and
SolarSPELL's attribution/licence are unchanged.

## Interface direction

- Visual thesis: a calm, light knowledge workspace with readable graphite text,
  warm amber actions and a restrained dark wordmark.
- Content: library navigation, nested sections, documents; curator forms add exact
  library/section placement beside original-file and source metadata controls.
- Interaction: dependent section choices and inline creation keep placement clear;
  standard Material UI dialogs and focus feedback keep the workflow predictable.
  Avoid decorative motion in a document management form.
