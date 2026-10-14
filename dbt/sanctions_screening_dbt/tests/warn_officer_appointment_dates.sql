-- O2, O3. Appointed under 16, or appointed before the company was
-- incorporated. Source errors, kept. Known 0 each.
{{ config(severity='warn') }}

select o.appointment_id, 'appointed under 16' as issue
from {{ ref('stg_ch_officer') }} as o
where o.officer_kind = 'person'
  and o.appointed_on is not null and o.birth_year is not null
  and make_date(o.birth_year, coalesce(o.birth_month, 1), 1)
      > o.appointed_on - interval '16 years'

union all

select o.appointment_id, 'appointed before incorporation'
from {{ ref('stg_ch_officer') }} as o
join {{ ref('stg_ch_company') }} as c using (company_number)
where o.appointed_on < c.incorporated_on
