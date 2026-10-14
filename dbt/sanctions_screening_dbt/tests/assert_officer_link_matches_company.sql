-- O1. The appointment's self link names the company it was fetched for, and
-- every appointment links to an officer. Otherwise an alert would point at
-- the wrong company or officer. Known 0.
select company_number, raw -> 'links' as links
from {{ source('raw', 'raw_ch_officer') }}
where split_part(raw -> 'links' ->> 'self', '/', 3) <> company_number
   or nullif(raw -> 'links' -> 'officer' ->> 'appointments', '') is null
