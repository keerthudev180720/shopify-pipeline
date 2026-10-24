-- Grain: one row per order. Rolls up fct_order_lines and adds customer order sequence
-- (1st order, 2nd order, ...) used for new vs returning and repeat-purchase metrics.
with lines  as (select * from {{ ref('fct_order_lines') }}),
     orders as (select * from {{ ref('stg_shopify__orders') }}),

rolled as (
    select
        order_id,
        count(*)              as line_count,
        sum(quantity)         as units,
        sum(gross_sales)      as gross_sales,
        sum(discount_amount)  as discount_amount,
        sum(net_sales)        as net_sales,
        sum(cogs)             as cogs,
        sum(refunded_amount)  as refunded_amount,
        sum(net_revenue)      as net_revenue,
        boolor_agg(is_refunded) as has_refund
    from lines
    group by 1
),

joined as (
    select
        o.order_id,
        o.order_number,
        coalesce(o.customer_id, 'GUEST')                         as customer_key,
        o.is_guest,
        o.processed_at,
        {{ local_date('o.processed_at') }}                       as order_date,
        o.financial_status,
        (o.cancelled_at is not null)                             as is_cancelled,
        o.is_test,
        o.is_seeded,
        (not o.is_seeded or o.is_test)                           as is_excluded_from_reporting,  -- internal/test orders
        r.line_count, r.units, r.gross_sales, r.discount_amount, r.net_sales,
        r.cogs, r.refunded_amount, r.net_revenue, r.has_refund,
        o.total_price                                            as shopify_total_price  -- kept for reconciliation
    from orders o
    left join rolled r on r.order_id = o.order_id
),

sequenced as (
    select
        *,
        case when not is_guest then
            row_number() over (partition by customer_key order by processed_at, order_id)
        end                                                      as customer_order_sequence
    from joined
)

select *, coalesce(customer_order_sequence = 1, false) as is_first_order
from sequenced
