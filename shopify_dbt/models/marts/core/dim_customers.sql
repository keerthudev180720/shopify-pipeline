-- Grain: one row per customer, plus one 'GUEST' row so guest orders still join.
-- Segment is DERIVED from order behavior (the seeder's hidden labels are never used).
-- Acquisition date = first order date (Shopify's createdAt is just when the record was made).
with customers as (select * from {{ ref('stg_shopify__customers') }}),

orders as (
    select * from {{ ref('fct_orders') }}
    where not is_cancelled and not is_test and not is_guest
),

stats as (
    select
        customer_key,
        count(*)            as order_count,
        min(processed_at)   as first_order_at,
        max(processed_at)   as last_order_at,
        sum(net_sales)      as lifetime_net_sales,
        sum(refunded_amount) as lifetime_refunds,
        sum(net_revenue)    as lifetime_net_revenue
    from orders
    group by 1
),

registered as (
    select
        c.customer_id                                            as customer_key,
        c.customer_id,
        c.created_at                                             as record_created_at,
        c.account_state,
        c.is_seeded,
        coalesce(s.order_count, 0)                               as order_count,
        s.first_order_at,
        s.last_order_at,
        date_trunc('month', {{ local_date('s.first_order_at') }}) as acquisition_month,
        coalesce(s.lifetime_net_sales, 0)                        as lifetime_net_sales,
        coalesce(s.lifetime_refunds, 0)                          as lifetime_refunds,
        coalesce(s.lifetime_net_revenue, 0)                      as lifetime_net_revenue,
        case
            when coalesce(s.order_count, 0) >= {{ var('vip_min_orders') }}    then 'vip'
            when coalesce(s.order_count, 0) >= {{ var('repeat_min_orders') }} then 'repeat'
            when coalesce(s.order_count, 0) = 1                               then 'one_time'
            else 'no_purchase'
        end                                                      as customer_segment,
        c.shopify_order_count                                    -- Shopify's own count, for reconciliation
    from customers c
    left join stats s on s.customer_key = c.customer_id
)

select * from registered
union all
select
    'GUEST', null, null, null, false,
    null, null, null, null, null, null, null,
    'guest', null
