# Oasis Knowledge brand

Oasis Knowledge is the collection and its curator workspace. It contains named
**libraries**, and each library contains **sections** and original documents.
Sections may contain further sections. Oasis remains the conversational interface.

## Approved logo

The catalogue, private curator workspace and administrator account screens use
Kuwala's approved **A · Small gap** sun, power and conversation mark. The readable
product label remains beside the decorative image. The mark sits on a
Graphite tile and reduces from 40px to 32px on narrow screens. No document artwork,
folder image, uploaded asset, original file or attribution record is changed.

The exact canonical vector is kept in `design/brand/kuwala-oasis.svg`; its SHA-256 is
`3fa3bf3bd3c07191e2180d05c016fc8faa1df72f0489edbc24dfa76d9fb7fce1`.
`frontend/src/images/kuwala-oasis.svg` is a byte-identical runtime copy. The SVG
favicon, 16/32/48px ICO, 32px PNG and 180px touch icon are the exact derivatives
from the station repository's `scripts/export_brand.mjs`. Webpack copies them into
this manager's own `/static/images/` namespace; neither the manager nor its login
screen requests assets from the station, website or internet at runtime.

After an approved artwork update, regenerate the derivatives in the station
repository, copy its canonical vectors into this fork's `design/brand/`, and copy
the mark and four icons into `frontend/src/images/`. Update the recorded approved
hashes in `frontend/scripts/test-brand.js`, rebuild and run:

```sh
npm --prefix frontend run build-prod
node --test frontend/scripts/test-brand.js
python manage.py test content_management.test_curator_auth --settings=dlms.preview_settings
```

The brand change is a code release using the existing
[device deployment procedure](OASIS_DEVICE_DEPLOYMENT.md). Wait for its exact
merged-commit CI and idle maintenance acknowledgement, then preserve the current
catalogue, media, indexes, account credentials and station fingerprint. It does
not require a data import, a new public route or a restored backup. Administrator
sessions, origin checks and the private Tailscale listener retain their existing
access rules.

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
