-- Subject organisation cores never end in a UK legal form: if one does,
-- stripping failed (as "HOOVER TRUST FUND LIMITED THE" did) and the extra
-- word lowers every match score for that company. Known 0.
select entity_id, name_raw, name_core
from {{ ref('int_name_norm') }}
where side = 'subject' and entity_kind = 'organization'
  and name_core ~ ' (LIMITED|LTD|PLC|LLP)( THE)?$'
