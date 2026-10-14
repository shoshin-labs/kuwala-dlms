"""Bounded catalogue originals/reviews shared by curator maintenance adapters.

The station retains authoritative extraction, hash, scope and artifact checks.
These ceilings must agree with app.library.index on the commissioned station.
ZIP bounds remain independent from the reviewed passage-manifest schema.
"""

MAX_DOCUMENTS = 512
MAX_MANIFEST_BYTES = 2 * 1024 * 1024
MAX_PDF_BYTES = 256 * 1024 * 1024
