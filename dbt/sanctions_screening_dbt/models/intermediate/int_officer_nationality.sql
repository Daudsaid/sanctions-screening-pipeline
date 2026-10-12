-- Free-text nationality to ISO codes. Values are split into tokens on
-- , / & " and " " - ", filler words are stripped, and each token is looked
-- up in the nationality_token_iso seed. Unmatched tokens keep iso2 = null.
with src as (
    select
        appointment_id,
        nationality as nationality_raw,
        replace(
            replace(upper(nationality), 'ANTIGUA AND BARBUDA', 'ANTIGUA_BARBUDA'),
            '(JOINT)', ''
        ) as prepared
    from {{ ref('stg_ch_officer') }}
    where officer_kind = 'person' and nationality is not null
),

tokens as (
    select
        s.appointment_id,
        s.nationality_raw,
        regexp_replace(
            regexp_replace(trim(t.token), '^(CITIZEN OF|DUAL|WHITE)\s+', ''),
            '\s+(CITIZEN|NATIONAL)$', ''
        ) as token
    from src as s
    cross join lateral unnest(
        regexp_split_to_array(s.prepared, '\s*(,|/|&|\sAND\s|\s-\s)\s*')
    ) as t(token)
)

select
    t.appointment_id,
    t.nationality_raw,
    t.token,
    n.iso2
from tokens as t
left join {{ ref('nationality_token_iso') }} as n on n.token = t.token
where t.token <> ''
