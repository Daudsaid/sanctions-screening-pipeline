-- C4. Registered-office country is a UK spelling or blank. Not used for
-- matching. Known 2,511 ENGLAND, 2,104 UNITED KINGDOM, 547 blank,
-- 170 SCOTLAND, 45 WALES, 29 NORTHERN IRELAND; 0 other.
{{ config(severity='warn') }}

select company_number, raw ->> 'RegAddress.Country' as country
from {{ source('raw', 'raw_ch_company') }}
where coalesce(trim(raw ->> 'RegAddress.Country'), '') not in
      ('', 'ENGLAND', 'UNITED KINGDOM', 'SCOTLAND', 'WALES', 'NORTHERN IRELAND')
