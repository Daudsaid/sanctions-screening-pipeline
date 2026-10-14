-- O6. The same name and birth month under several officer IDs: Companies
-- House holds duplicate records for some people. Not merged, so one person
-- can alert twice. Known 645 groups covering 1,437 IDs.
{{ config(severity='warn') }}

select upper(name_raw) as name, birth_year, birth_month,
       count(distinct officer_id) as officer_ids
from {{ ref('stg_ch_officer') }}
where officer_kind = 'person' and birth_year is not null
group by 1, 2, 3
having count(distinct officer_id) > 1
