-- Company names ending in "(THE)" ("HOOVER TRUST FUND LIMITED(THE)").
-- THE is stripped from both ends by the legal_forms seed, so the legal form
-- before it is stripped too. Known 2.
{{ config(severity='warn') }}

select company_number, name
from {{ ref('stg_ch_company_name') }}
where name ~* '\(THE\)\s*$'
