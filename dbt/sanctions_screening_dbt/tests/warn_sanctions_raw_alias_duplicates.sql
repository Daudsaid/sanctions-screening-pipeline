-- S4. Source quirk: a target lists the same name twice (alias equals primary,
-- or alias repeated). Deduplicated in stg_sanctions_name. Known 10.
{{ config(severity='warn') }}

select target_id, upper(trim(n)) as name, count(*) as n
from {{ ref('stg_sanctions_target') }}
cross join lateral unnest(aliases || primary_name) as n
group by 1, 2
having count(*) > 1
