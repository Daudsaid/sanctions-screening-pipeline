-- C3. Previous-name fields from the bulk file: no gap in PreviousName_1..10
-- and every change date parses as dd/mm/yyyy (unparsed dates become null in
-- stg_ch_company_name). Known 0.
{{ config(severity='warn') }}

select r.company_number, i, 'gap in sequence' as issue
from {{ source('raw', 'raw_ch_company') }} as r
cross join generate_series(1, 9) as i
where nullif(trim(r.raw ->> ('PreviousName_' || i || '.CompanyName')), '') is null
  and nullif(trim(r.raw ->> ('PreviousName_' || (i + 1) || '.CompanyName')), '') is not null

union all

select r.company_number, i, 'unparseable change date'
from {{ source('raw', 'raw_ch_company') }} as r
cross join generate_series(1, 10) as i
where nullif(trim(r.raw ->> ('PreviousName_' || i || '.CONDATE')), '') is not null
  and r.raw ->> ('PreviousName_' || i || '.CONDATE') !~ '^\d{2}/\d{2}/\d{4}$'
