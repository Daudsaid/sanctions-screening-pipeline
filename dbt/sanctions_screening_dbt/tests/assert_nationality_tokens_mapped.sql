-- Warns, rather than fails, on nationality tokens the seed does not cover,
-- so a new spelling in a future load is visible without blocking the build.
{{ config(severity='warn') }}

select token, count(*) as officers
from {{ ref('int_officer_nationality') }}
where iso2 is null and token <> 'OTHER'
group by token
