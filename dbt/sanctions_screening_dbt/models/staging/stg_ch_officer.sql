-- Person names arrive as "SURNAME, Forenames, Title". Everything after the
-- second comma is a title field (courtesy titles, sometimes job titles) and
-- is kept out of the matching name. Bracketed text (nicknames, former names)
-- moves to name_note. A leading title in the forenames is stripped.
-- Repeated commas ("SURNAME,, Forenames") are collapsed before splitting.
-- A company filed under a person role arrives split like a person
-- ("LIMITED, Propensions"); when the surname field ends in a legal form it
-- becomes an organization named "Propensions LIMITED" (filed_as_person).
with latest as (
    select
        *,
        split_part(raw -> 'links' ->> 'self', '/', 5) as appointment_id,
        row_number() over (
            partition by split_part(raw -> 'links' ->> 'self', '/', 5)
            order by ingested_at desc, id desc
        ) as rn
    from {{ source('raw', 'raw_ch_officer') }}
),

shaped as (
    select
        appointment_id,
        split_part(raw -> 'links' -> 'officer' ->> 'appointments', '/', 3) as officer_id,
        company_number,
        raw ->> 'officer_role' as officer_role,
        case
            when raw ->> 'officer_role' like 'corporate%' then 'organization'
            else 'person'
        end as role_kind,
        raw ->> 'name' as name_raw,
        regexp_replace(raw ->> 'name', ',(\s*,)+', ',', 'g') as name_split,
        nullif(trim(raw ->> 'nationality'), '') as nationality,
        nullif(raw ->> 'country_of_residence', '') as country_of_residence,
        (raw -> 'date_of_birth' ->> 'year')::int as birth_year,
        (raw -> 'date_of_birth' ->> 'month')::int as birth_month,
        (raw ->> 'appointed_on')::date as appointed_on,
        (raw ->> 'resigned_on')::date as resigned_on,
        coalesce((raw ->> 'is_pre_1992_appointment')::boolean, false) as is_pre_1992_appointment,
        source_version,
        ingested_at
    from latest
    where rn = 1
),

parts as (
    select
        *,
        case when role_kind = 'person' and name_split like '%,%'
            then split_part(name_split, ',', 1) end as surname_part,
        case when role_kind = 'person' and name_split like '%,%'
            then split_part(name_split, ',', 2) end as forenames_part,
        case when role_kind = 'person'
            then nullif(trim(substring(name_split from '^[^,]*,[^,]*,(.*)$')), '') end as name_title,
        case when role_kind = 'person'
            then substring(split_part(name_split, ',', 1) || ' ' || split_part(name_split, ',', 2)
                           from '\(([^)]*)\)') end as name_note
    from shaped
),

kinds as (
    select
        *,
        coalesce(trim(surname_part) ~* '(^|\s)(LIMITED|LTD|LLP|PLC)$', false) as filed_as_person
    from parts
),

cleaned as (
    select
        *,
        trim(regexp_replace(surname_part, '\s*\([^)]*\)', '', 'g')) as surname,
        trim(regexp_replace(
            regexp_replace(forenames_part, '\s*\([^)]*\)', '', 'g'),
            '^\s*(LORD|SIR|DR|DAME|LADY|REV|PROF|MR|MRS|MS|MISS)\.?\s+', '', 'i'
        )) as forenames
    from kinds
)

select
    appointment_id,
    officer_id,
    company_number,
    officer_role,
    case when filed_as_person then 'organization' else role_kind end as officer_kind,
    filed_as_person,
    name_raw,
    case when not filed_as_person then surname end as surname,
    case when not filed_as_person then forenames end as forenames,
    case when not filed_as_person then name_title end as name_title,
    case when not filed_as_person then name_note end as name_note,
    case
        when filed_as_person
            then trim(trim(forenames_part) || ' ' || trim(surname_part))
        when role_kind = 'person' and surname is not null
            then trim(coalesce(forenames, '') || ' ' || surname)
        else name_raw
    end as full_name,
    nationality,
    country_of_residence,
    birth_year,
    birth_month,
    appointed_on,
    resigned_on,
    is_pre_1992_appointment,
    resigned_on is null as is_current,
    source_version,
    ingested_at
from cleaned
