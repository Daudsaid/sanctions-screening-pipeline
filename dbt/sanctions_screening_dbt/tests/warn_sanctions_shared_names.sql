-- S5. In-scope sanctions targets that share a primary name (two separate
-- persons named ALIREZA DERAKHSHAN). Alerts reference target_id, never a
-- name alone. Known 10 names.
{{ config(severity='warn') }}

select upper(primary_name) as name, count(*) as targets
from {{ ref('stg_sanctions_target') }}
where entity_group in ('person', 'organization')
group by 1
having count(*) > 1
