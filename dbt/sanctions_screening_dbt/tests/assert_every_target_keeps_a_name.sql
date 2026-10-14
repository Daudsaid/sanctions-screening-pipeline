-- Every person or organisation sanctions target keeps at least one name
-- after non-Latin and mixed-script names are dropped. A target with no
-- name can never alert. Known 0 (5,413 non-Latin and 320 mixed-script
-- names dropped, no target emptied).
select t.target_id, t.entity_group, t.primary_name
from {{ ref('stg_sanctions_target') }} as t
where t.entity_group in ('person', 'organization')
  and not exists (
      select 1
      from {{ ref('int_name_norm') }} as n
      where n.side = 'target' and n.entity_id = t.target_id
  )
