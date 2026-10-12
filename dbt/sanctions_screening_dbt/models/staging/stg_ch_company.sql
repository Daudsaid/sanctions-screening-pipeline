select
    company_number,
    raw ->> 'CompanyName' as company_name,
    raw ->> 'CompanyCategory' as company_category,
    raw ->> 'CompanyStatus' as company_status,
    to_date(raw ->> 'IncorporationDate', 'DD/MM/YYYY') as incorporated_on,
    nullif(raw ->> 'RegAddress.PostCode', '') as postcode,
    nullif(raw ->> 'CountryOfOrigin', '') as country_of_origin,
    array_remove(array[
        split_part(raw ->> 'SICCode.SicText_1', ' - ', 1),
        split_part(raw ->> 'SICCode.SicText_2', ' - ', 1),
        split_part(raw ->> 'SICCode.SicText_3', ' - ', 1),
        split_part(raw ->> 'SICCode.SicText_4', ' - ', 1)
    ], '') as sic_codes,
    source_version,
    ingested_at
from {{ ref('base_ch_company') }}
