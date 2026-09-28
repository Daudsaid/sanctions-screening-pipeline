
<!-- Sanctions source: OFAC over OFSI for v1 -->

<!-- Attempted to use gb_hmt_sanctions (UK OFSI list) as the primary sanctions
source. As of 2026-09-19, OpenSanctions' bulk export for this dataset
returns a header-only CSV (175 bytes) at the origin (confirmed via
x-goog-stored-content-length on the GCS-backed CDN response, not just a
stale cache — a fresh cache-busted request returned the same result).

Used us_ofac_sdn instead for v1: same schema, confirmed 20,349 rows,
correctly structured. UK OFSI coverage can be added back once the
upstream export is fixed, or pulled directly from GOV.UK's own OFSI
consolidated list CSV as an alternative source. -->

## Idempotent raw loads: hashing excludes volatile fields

The first version hashed the whole source row to detect changes. A second
run doubled the table (20,346 to 40,692 rows) because OpenSanctions
re-stamps last_seen on every export, so every record looked new even though
nothing about the sanctioned party had changed. last_change was identical
across the two copies, which confirmed the diagnosis.

The hash now excludes last_seen. The column is still stored in the raw JSON;
it just doesn't decide whether a record counts as changed. A record only
lands as a new version when its content changes, which is what the audit
trail needs. Verified: a second run against an unchanged export loads 0 rows.
