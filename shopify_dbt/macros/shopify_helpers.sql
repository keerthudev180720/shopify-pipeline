{# Shopify money objects look like {"shopMoney": {"amount": "12.50"}} -> DECIMAL(12,2) #}
{% macro money(path) -%}
    {{ path }}:shopMoney:amount::number(12, 2)
{%- endmacro %}

{# Shopify timestamps are ISO-8601 with 'Z' -> store as UTC TIMESTAMP_NTZ #}
{% macro to_utc(path) -%}
    convert_timezone('UTC', {{ path }}::timestamp_tz)::timestamp_ntz
{%- endmacro %}

{# UTC timestamp -> calendar date in the store's local time zone (business reporting date) #}
{% macro local_date(ts) -%}
    convert_timezone('UTC', '{{ var("store_timezone") }}', {{ ts }})::date
{%- endmacro %}
