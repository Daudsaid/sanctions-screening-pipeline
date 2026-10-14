-- Volume guard per sanctions list. Fewer rows than the floor means a
-- truncated or empty export, like the header-only OFSI CSV in 2026-09
-- (see docs/decisions.md); a list missing entirely counts as 0 rows.
-- Known 2026-10: us_ofac_sdn 20,394, gb_fcdo_sanctions 6,411.
-- Disabled when min_rows_check is false (CI builds on an empty database).
{{ config(enabled=var('min_rows_check', true) | as_bool) }}

with floors (dataset, min_rows) as (
    values ('us_ofac_sdn', 15000), ('gb_fcdo_sanctions', 4500)
),

screened as (
    select f.dataset, f.min_rows
    from floors as f
    where f.dataset in (
        {%- for d in var('sanctions_datasets') %}'{{ d }}'{{ ", " if not loop.last }}{% endfor -%}
    )
)

select s.dataset, s.min_rows, count(l.target_id) as rows_found
from screened as s
left join {{ ref('stg_sanctions_listing') }} as l using (dataset)
group by s.dataset, s.min_rows
having count(l.target_id) < s.min_rows
