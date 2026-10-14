-- S6. OpenSanctions timestamps in order: first_seen <= last_change <= last_seen.
-- Not used in screening. Known 0.
{{ config(severity='warn') }}

select target_id, raw ->> 'first_seen' as first_seen,
       raw ->> 'last_change' as last_change, raw ->> 'last_seen' as last_seen
from {{ source('raw', 'raw_sanctions_snapshot') }}
where (raw ->> 'first_seen')::timestamp > (raw ->> 'last_seen')::timestamp
   or (raw ->> 'last_change')::timestamp > (raw ->> 'last_seen')::timestamp
   or (raw ->> 'last_change')::timestamp < (raw ->> 'first_seen')::timestamp
