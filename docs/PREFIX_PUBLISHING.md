# Reviewed-prefix publishing

Date: 2026-09-23. Problem: any tip landing staled a book's entire review
set, dropped the book from the site, and failed the whole ship -- coupling
translation cadence to publishing. Fix: publish the reviewed leading
prefix; hold only the unreviewed tail.

## Rules (fail-closed)

1. Provisional scope digest matches -> whole work publishes (unchanged).
2. Else the scope packet must validate AND its reviewed scope must be a
   leading prefix of current sections with identical metadata.
   Anything else (reorder, drop, middle edit, metadata change) holds the
   whole work, exactly as before.
3. Sections past the reviewed prefix are held as `unreviewed_tail`
   (receipt key `held_tail_sections`), never published, never in the
   search index. The gate asserts their absence from dist.
4. Partition (scaffold/quality) holds stay whole-work and strict: only
   the review-timing gate does prefix publishing.

## Declared-scope packets

`make_audit_packet(..., expected_sections=[...])` freezes the reviewed set.
Full-selection declared packets tolerate appended rows (recorded as
`unreviewed_extra`); edited/removed declared rows, raw-witness changes, and
sampling packets behave exactly as before. Packets without the flag keep
legacy whole-file binding: one regeneration migrates them.

## Punch procedure for densify lanes

1. Land tips as usual (no ship pressure mid-cycle).
2. Regenerate the scope packet with declared scope:
   `scripts/regen_declared_packet.py` (translations repo). It refuses when
   declared history changed.
3. Write the receipt by genuine review of the new tail; update the manifest
   scope_reviews + per-section reviews entries.
4. Ship. Between punches the site serves the last reviewed tip.
