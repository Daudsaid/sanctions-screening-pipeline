-- One row per sanctions list per target: the latest version of each record
-- in each OpenSanctions dataset, for targets still in that list's latest
-- export. Raw snapshots are append-only, so a delisted target keeps its old
-- rows there; raw_sanctions_load says which ids the latest export held.
-- stg_sanctions_target merges the lists. var sanctions_datasets chooses
-- which lists are screened.
with latest_load as (
    select distinct on (dataset) dataset, target_ids
    from {{ source('raw', 'raw_sanctions_load') }}
    order by dataset, loaded_at desc, load_id desc
),

listed as (
    select dataset, unnest(target_ids) as target_id
    from latest_load
),

latest as (
    select
        s.*,
        row_number() over (
            partition by s.dataset, s.target_id
            order by s.ingested_at desc, s.id desc
        ) as rn
    from {{ source('raw', 'raw_sanctions_snapshot') }} as s
    join listed as l using (dataset, target_id)
    where s.dataset in (
        {%- for d in var('sanctions_datasets') %}'{{ d }}'{{ ", " if not loop.last }}{% endfor -%}
    )
)

select
    target_id,
    dataset,
    raw ->> 'schema' as entity_type,
    case
        when raw ->> 'schema' = 'Person' then 'person'
        when raw ->> 'schema' in ('Organization', 'Company', 'LegalEntity') then 'organization'
        else 'out_of_scope'
    end as entity_group,
    raw ->> 'name' as primary_name,
    coalesce(string_to_array(nullif(raw ->> 'aliases', ''), ';'), '{}') as aliases,
    coalesce(string_to_array(nullif(raw ->> 'birth_date', ''), ';'), '{}') as birth_dates,
    coalesce(string_to_array(nullif(raw ->> 'countries', ''), ';'), '{}') as countries,
    coalesce(string_to_array(nullif(raw ->> 'program_ids', ''), ';'), '{}') as program_ids,
    nullif(raw ->> 'last_change', '')::timestamp as last_change,
    source_version,
    ingested_at
from latest
where rn = 1
