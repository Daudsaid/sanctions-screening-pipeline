-- O1. Every company in the slice has at least one officer record. A gap
-- means the officers crawl missed it. Known 0.
{{ config(severity='warn') }}

select c.company_number
from {{ ref('stg_ch_company') }} as c
where not exists (
    select 1 from {{ ref('stg_ch_officer') }} as o
    where o.company_number = c.company_number
)
