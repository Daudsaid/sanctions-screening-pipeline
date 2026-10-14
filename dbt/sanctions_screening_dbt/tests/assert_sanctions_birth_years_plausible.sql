-- S2. Sanctions birth years between 1900 and this year. A wrong year turns
-- into a -40 birth-date conflict in scoring. Known 0 (range 1921-2006).
select target_id, d as birth_date
from {{ ref('stg_sanctions_target') }}
cross join lateral unnest(birth_dates) as d
where d ~ '^\d{4}'
  and left(d, 4)::int not between 1900 and extract(year from current_date)
