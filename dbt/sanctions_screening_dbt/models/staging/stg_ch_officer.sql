-- Person names arrive as "SURNAME, Forenames, Title". Everything after the
-- second comma is a title field (courtesy titles, sometimes job titles) and
-- is kept out of the matching name. Bracketed text (nicknames, former names)
-- moves to name_note. A leading title in the forenames is stripped.
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
        end as officer_kind,
        raw ->> 'name' as name_raw,
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
        case when officer_kind = 'person' and name_raw like '%,%'
            then split_part(name_raw, ',', 1) end as surname_part,
        case when officer_kind = 'person' and name_raw like '%,%'
            then split_part(name_raw, ',', 2) end as forenames_part,
        case when officer_kind = 'person'
            then nullif(trim(substring(name_raw from '^[^,]*,[^,]*,(.*)$')), '') end as name_title,
        case when officer_kind = 'person'
            then substring(split_part(name_raw, ',', 1) || ' ' || split_part(name_raw, ',', 2)
                           from '\(([^)]*)\)') end as name_note
    from shaped
),

cleaned as (
    select
        *,
        trim(regexp_replace(surname_part, '\s*\([^)]*\)', '', 'g')) as surname,
        trim(regexp_replace(
            regexp_replace(forenames_part, '\s*\([^)]*\)', '', 'g'),
            '^\s*(LORD|SIR|DR|DAME|LADY|REV|PROF|MR|MRS|MS|MISS)\.?\s+', '', 'i'
        )) as forenames
    from parts
)

select
    appointment_id,
    officer_id,
    company_number,
    officer_role,
    officer_kind,
    name_raw,
    surname,
    forenames,
    name_title,
    name_note,
    case
        when officer_kind = 'person' and surname is not null
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
