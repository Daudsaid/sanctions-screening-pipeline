{#
  Shared name normalisation, applied identically to subjects and targets.
  Dots and apostrophes are removed without a space (LTD. -> LTD,
  S.A. -> SA, JAZA'IRI -> JAZAIRI); other punctuation becomes a space;
  accents are removed; whitespace is collapsed. Non-Latin script survives
  unaccent but is removed by the A-Z filter, leaving an empty string.
#}
{% macro normalise_name(col) %}
trim(regexp_replace(
    upper(unaccent(translate({{ col }}, '.''’', ''))),
    '[^A-Z0-9]+', ' ', 'g'
))
{% endmacro %}
