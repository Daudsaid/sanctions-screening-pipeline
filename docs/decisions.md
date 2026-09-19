
## Sanctions source: OFAC over OFSI for v1

Attempted to use gb_hmt_sanctions (UK OFSI list) as the primary sanctions
source. As of 2026-09-19, OpenSanctions' bulk export for this dataset
returns a header-only CSV (175 bytes) at the origin (confirmed via
x-goog-stored-content-length on the GCS-backed CDN response, not just a
stale cache — a fresh cache-busted request returned the same result).

Used us_ofac_sdn instead for v1: same schema, confirmed 20,349 rows,
correctly structured. UK OFSI coverage can be added back once the
upstream export is fixed, or pulled directly from GOV.UK's own OFSI
consolidated list CSV as an alternative source.
