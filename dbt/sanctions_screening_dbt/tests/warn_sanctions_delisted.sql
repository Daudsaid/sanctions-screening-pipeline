-- Targets with raw rows that are missing from their list's latest export:
-- delisted, or re-issued by OpenSanctions under a new id. They are not
-- screened. Known 187 on us_ofac_sdn after the 2026-10 reload (55 of them
-- share a name with a current target, so most look like new ids).
{{ config(severity='warn') }}

with latest_load as (
    select distinct on (dataset) dataset, target_ids
    from {{ source('raw', 'raw_sanctions_load') }}
    order by dataset, loaded_at desc, load_id desc
),

listed as (
    select dataset, unnest(target_ids) as target_id
    from latest_load
)

select distinct s.dataset, s.target_id
from {{ source('raw', 'raw_sanctions_snapshot') }} as s
join latest_load using (dataset)
left join listed as l using (dataset, target_id)
where l.target_id is null
