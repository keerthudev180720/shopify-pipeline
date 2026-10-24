-- Completeness: every staged order must reach fct_orders (no rows lost in joins).
-- A test FAILS if this query returns any rows.
with counts as (
    select
        (select count(*) from {{ ref('stg_shopify__orders') }}) as staging_orders,
        (select count(*) from {{ ref('fct_orders') }})          as fact_orders
)
select * from counts
where staging_orders != fact_orders
