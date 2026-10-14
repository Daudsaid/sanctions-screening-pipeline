-- S4. Source quirk: a list gives a target the same name twice (alias equals
-- primary, or alias repeated). Deduplicated in stg_sanctions_name. Known 10
-- on us_ofac_sdn at the 2026-09 load.
{{ config(severity='warn') }}

select dataset, target_id, upper(trim(n)) as name, count(*) as n
from {{ ref('stg_sanctions_listing') }}
cross join lateral unnest(aliases || primary_name) as n
group by 1, 2, 3
having count(*) > 1
