-- A target that one list calls a person and another an organisation. The
-- merge takes the UK listing's kind, so the other list's view is lost.
-- Known 0 (138 targets differ only between Company and Organization, which
-- are the same group).
{{ config(severity='warn') }}

select target_id, array_agg(distinct entity_group) as groups
from {{ ref('stg_sanctions_listing') }}
group by target_id
having count(distinct entity_group) > 1
