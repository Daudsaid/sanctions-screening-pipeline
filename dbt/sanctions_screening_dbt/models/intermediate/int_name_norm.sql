-- Every name of every subject and target, normalised identically.
-- Subjects: current person officers, current corporate officers, and all
-- companies under current and previous names. Targets: sanctions names
-- whose group is person or organization. Organisation names also get
-- name_core, with legal forms (seed legal_forms) stripped from both ends.

with forms as (
    select
        string_agg(phrase, '|' order by length(phrase) desc)
            filter (where position in ('prefix', 'both')) as prefix_re,
        string_agg(phrase, '|' order by length(phrase) desc)
            filter (where position in ('suffix', 'both')) as suffix_re
    from {{ ref('legal_forms') }}
),

all_names as (
    select 'subject' as side, 'person' as entity_kind, 'officer' as entity_type,
           officer_id as entity_id, full_name as name_raw
    from {{ ref('stg_ch_officer') }}
    where officer_kind = 'person' and is_current

    union

    select 'subject', 'organization', 'officer', officer_id, full_name
    from {{ ref('stg_ch_officer') }}
    where officer_kind = 'organization' and is_current

    union

    select 'subject', 'organization', 'company', company_number, name
    from {{ ref('stg_ch_company_name') }}

    union

    select 'target', entity_group, 'sanctions_target', target_id, name
    from {{ ref('stg_sanctions_name') }}
    where entity_group in ('person', 'organization')
),

normed as (
    select *, {{ normalise_name('name_raw') }} as name_norm
    from all_names
),

cored as (
    select
        n.*,
        case
            when n.entity_kind = 'organization' then coalesce(
                nullif(trim(regexp_replace(
                    regexp_replace(n.name_norm, '^((' || f.prefix_re || ')\s+)+', ''),
                    '(\s+(' || f.suffix_re || '))+$', ''
                )), ''),
                n.name_norm
            )
            else n.name_norm
        end as name_core
    from normed as n
    cross join forms as f
    where n.name_norm <> ''
      -- NEW: mixed-script names (Cyrillic with stray Latin letters, such as a
      -- Belarusian i, a Latin C, or OOO before a Cyrillic name) normalise to
      -- junk like C, I I I or OOO. Keep a name only if at least half of its
      -- letters are Latin.
      and length(regexp_replace(unaccent(n.name_raw), '[^A-Za-z]', '', 'g'))
          >= 0.5 * length(regexp_replace(n.name_raw, '[^[:alpha:]]', '', 'g'))
),

deduped as (
    select distinct on (side, entity_type, entity_id, name_core) *
    from cored
    order by side, entity_type, entity_id, name_core, name_raw
)

select
    md5(side || '|' || entity_type || '|' || entity_id || '|' || name_core) as name_id,
    side,
    entity_kind,
    entity_type,
    entity_id,
    name_raw,
    name_norm,
    name_core,
    array_to_string(
        array(select t from unnest(string_to_array(name_core, ' ')) as t order by t),
        ' '
    ) as name_sorted
from deduped
