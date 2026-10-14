-- O5. One officer ID with more than one name or birth date across its
-- appointments. Every name is matched, like aliases. Known 38 IDs with
-- several names, 1 with two birth dates.
{{ config(severity='warn') }}

select officer_id, 'several names' as issue
from {{ ref('stg_ch_officer') }}
where officer_kind = 'person'
group by officer_id
having count(distinct name_raw) > 1

union all

select officer_id, 'several birth dates'
from {{ ref('stg_ch_officer') }}
where officer_kind = 'person' and birth_year is not null
group by officer_id
having count(distinct birth_year * 100 + birth_month) > 1
