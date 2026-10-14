-- C3. A previous name identical to the current one (a company that changed
-- name and changed back). Harmless: int_name_norm deduplicates names per
-- entity. Known 10.
{{ config(severity='warn') }}

select n.company_number, n.name
from {{ ref('stg_ch_company_name') }} as n
join {{ ref('stg_ch_company') }} as c using (company_number)
where n.name_type = 'previous' and n.name = c.company_name
