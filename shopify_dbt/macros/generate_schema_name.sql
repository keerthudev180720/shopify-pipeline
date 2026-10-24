{#
  dbt's default would build schemas named STAGING_STAGING / STAGING_MARTS
  (target schema + custom schema). We want exactly STAGING and MARTS.
#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- else -%}
        {{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
