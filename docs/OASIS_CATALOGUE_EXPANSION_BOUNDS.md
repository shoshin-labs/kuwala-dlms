# Bounded whole-book catalogue expansion

The 14 October 2026 selection adds 53 originals to the existing main catalogue.
Its largest original is 261,168,076 bytes and longest book is 1,003 pages.
All 53 passed complete native station text extraction on the Mac: 17,132 new
pages and 37,657 passages, with original SHA-256 preserved. The projected
combined reader contains 176 PDFs / 66,027 passages; two existing encrypted
authoring originals remain disabled. This is a measured package expansion,
not proof of thousands of searchable PDFs or advice/curriculum approval.

The curator now shares `dlms/library_limits.py` for a **512-document, 2 MiB
reviewed-manifest, 256 MiB original** ceiling. Station import/provider and
deployment checks use the same profile. Adoption and transfer retain exact
manifest/hash/folder validation; none silently approve or drop records.
The station also allows 2,000 pages, 4,000,000 characters and 4,000 passages
per document, 128,000 semantic passages and 512 MiB semantic artifacts.
Existing query deadlines, ranking and the installed Nomic model are unchanged.

Portable library ZIPs are separately limited to **256 MiB compressed and
512 MiB expanded**. This lets large individual books round-trip unchanged;
collections exceeding the archive bound must be exported as smaller packages.
The existing document/folder/metadata/archive validation, private origin,
CSRF and administrator login remain intact. Updating limits does not activate
a reader publication or build indexes.

The actual 53-document extraction has useful prose but incomplete font/formula
text in the Siyavula Grade 10 Physical Sciences teacher guide. Preserve its
native extraction warning and original page links; do not invent OCR text.

Focused catalogue transfer, indexing, adoption and portable-library suites
passed 64 tests, including a streamed 90 MiB padded synthetic original ZIP
round-trip, a review above the former 256 KiB bound, full 176/512-document
coverage and rejection beyond the finite limits. These fixtures test software
contracts; actual combined package startup/search measurements remain separate.

