with latest as (
    select
        *,
        row_number() over (
            partition by target_id
            order by ingested_at desc, id desc
        ) as rn
    from {{ source('raw', 'raw_sanctions_snapshot') }}
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
