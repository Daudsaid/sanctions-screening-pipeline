-- How many person officers had a title at the start of their forenames
-- before staging stripped it, by title. Whole leading words only, unlike
-- the substring check that reported 1,005 in the data-quality run.
-- Run: dbt compile -s leading_titles_in_forenames, then run the SQL in
-- target/compiled/.../analyses/ with psql.

select
    upper(substring(split_part(name_raw, ',', 2)
        from '^\s*(LORD|SIR|DR|DAME|LADY|REV|PROF|MR|MRS|MS|MISS)\.?(?:\s|$)')) as title,
    count(*) as appointments,
    count(distinct officer_id) as officer_ids
from {{ ref('stg_ch_officer') }}
where officer_kind = 'person'
  and split_part(name_raw, ',', 2) ~* '^\s*(LORD|SIR|DR|DAME|LADY|REV|PROF|MR|MRS|MS|MISS)\.?(\s|$)'
group by 1
order by 2 desc
