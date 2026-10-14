-- Officer names that staging has to repair before matching. Known 5 rows:
-- 3 current companies filed under a person role ("LIMITED, Propensions";
-- 5 including resigned), now screened as organisations, and 2 names with a
-- repeated comma: "SURNAME,, Forenames" (current), whose
-- forenames were lost before commas were collapsed, and a resigned officer
-- with ", ,Mr" in the title field.
{{ config(severity='warn') }}

select appointment_id, name_raw, 'company filed as person' as issue
from {{ ref('stg_ch_officer') }}
where filed_as_person and is_current

union all

select appointment_id, name_raw, 'repeated comma'
from {{ ref('stg_ch_officer') }}
where name_raw ~ ',\s*,'
