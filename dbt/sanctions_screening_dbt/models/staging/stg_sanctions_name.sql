-- One row per distinct name per target. Aliases that repeat the primary
-- name, or repeat each other, are dropped (profiling found 4 and 6).
with all_names as (
    select target_id, entity_group, trim(primary_name) as name, 'primary' as name_type
    from {{ ref('stg_sanctions_target') }}

    union all

    select t.target_id, t.entity_group, trim(a.alias), 'alias'
    from {{ ref('stg_sanctions_target') }} as t
    cross join lateral unnest(t.aliases) as a(alias)
    where trim(a.alias) <> ''
),

ranked as (
    select
        *,
        row_number() over (
            partition by target_id, upper(name)
            order by (name_type = 'primary') desc
        ) as rn
    from all_names
)

select target_id, entity_group, name, name_type
from ranked
where rn = 1
