select
    c.company_number,
    trim(v.name) as name,
    v.name_type,
    case
        when v.changed_on ~ '^\d{2}/\d{2}/\d{4}$' then to_date(v.changed_on, 'DD/MM/YYYY')
    end as name_changed_on
from {{ ref('base_ch_company') }} as c
cross join lateral (
    values
        (c.raw ->> 'CompanyName', 'current', null::text)
        {% for i in range(1, 11) %}
        , (c.raw ->> 'PreviousName_{{ i }}.CompanyName', 'previous', c.raw ->> 'PreviousName_{{ i }}.CONDATE')
        {% endfor %}
) as v(name, name_type, changed_on)
where nullif(trim(v.name), '') is not null
