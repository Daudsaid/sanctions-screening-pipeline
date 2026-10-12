{{ config(materialized='ephemeral') }}

select *
from (
    select
        *,
        row_number() over (
            partition by company_number
            order by ingested_at desc, id desc
        ) as rn
    from {{ source('raw', 'raw_ch_company') }}
) as t
where rn = 1
