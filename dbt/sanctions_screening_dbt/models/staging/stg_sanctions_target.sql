-- One row per sanctioned party, merged across lists. OpenSanctions gives a
-- party listed by both the UK and the US the same id, so they merge on
-- target_id. The UK listing's primary name is preferred; every other name
-- on either list becomes an alias, and birth dates, countries and programmes
-- are combined, so scoring sees everything either list says.
with listing as (
    select
        *,
        -- UK first: this pipeline screens UK companies.
        case dataset when 'gb_fcdo_sanctions' then 1 else 2 end as list_rank
    from {{ ref('stg_sanctions_listing') }}
),

merged as (
    select
        target_id,
        array_agg(dataset order by list_rank) as datasets,
        (array_agg(entity_type order by list_rank))[1] as entity_type,
        (array_agg(entity_group order by list_rank))[1] as entity_group,
        (array_agg(primary_name order by list_rank))[1] as primary_name,
        max(last_change) as last_change,
        max(ingested_at) as ingested_at
    from listing
    group by target_id
)

select
    m.target_id,
    m.datasets,
    m.entity_type,
    m.entity_group,
    m.primary_name,
    coalesce(array(
        select distinct n
        from listing as l
        cross join lateral unnest(l.aliases || l.primary_name) as n
        where l.target_id = m.target_id and n <> m.primary_name
        order by n
    ), '{}') as aliases,
    coalesce(array(
        select distinct d
        from listing as l
        cross join lateral unnest(l.birth_dates) as d
        where l.target_id = m.target_id
        order by d
    ), '{}') as birth_dates,
    coalesce(array(
        select distinct c
        from listing as l
        cross join lateral unnest(l.countries) as c
        where l.target_id = m.target_id
        order by c
    ), '{}') as countries,
    coalesce(array(
        select distinct p
        from listing as l
        cross join lateral unnest(l.program_ids) as p
        where l.target_id = m.target_id
        order by p
    ), '{}') as program_ids,
    m.last_change,
    m.ingested_at
from merged as m
