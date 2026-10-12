-- Warns when a person officer's forenames still start with a title after
-- staging has stripped one (e.g. "SIR DR JOHN" keeps DR). Matches whole
-- leading words only, so ANDREW, DREW and MRIDULA are not counted.
{{ config(severity='warn') }}

select appointment_id, name_raw, forenames
from {{ ref('stg_ch_officer') }}
where officer_kind = 'person'
  and forenames ~* '^(LORD|SIR|DR|DAME|LADY|REV|PROF|MR|MRS|MS|MISS)\.?(\s|$)'
