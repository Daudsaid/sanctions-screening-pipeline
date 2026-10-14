-- O3. Officers appointed before their company was incorporated. Source
-- error, kept. Known 0. Written as SQL because it joins two models, which
-- dbt-expectations does not cover.
{{ config(severity='warn') }}

select o.appointment_id, o.appointed_on, c.incorporated_on
from {{ ref('stg_ch_officer') }} as o
join {{ ref('stg_ch_company') }} as c using (company_number)
where o.appointed_on < c.incorporated_on
