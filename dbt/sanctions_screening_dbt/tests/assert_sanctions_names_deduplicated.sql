-- S4. Staging keeps one row per name per target, ignoring case. The raw
-- export has 4 aliases repeating the primary name and 6 repeating each
-- other; see warn_sanctions_raw_alias_duplicates for the source count.
select target_id, upper(name) as name, count(*) as n
from {{ ref('stg_sanctions_name') }}
group by 1, 2
having count(*) > 1
