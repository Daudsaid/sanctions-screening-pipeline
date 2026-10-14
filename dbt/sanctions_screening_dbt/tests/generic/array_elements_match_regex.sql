-- Fails for every element of a text[] column that does not match regex.
{% test array_elements_match_regex(model, column_name, regex) %}

select t.*, e.element
from {{ model }} as t
cross join lateral unnest(t.{{ column_name }}) as e(element)
where e.element !~ '{{ regex }}'

{% endtest %}
