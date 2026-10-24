-- Grain: one row per calendar day (store local time), including days with zero orders.
-- Two refund views, on purpose:
--   refunds_by_refund_date : money given back that day (finance / cash view)  -> used in net_revenue here
--   fct_orders.refunded_amount : refunds tied back to the original order date (cohort / product view)
with orders as (
    select * from {{ ref('fct_orders') }}
    where not is_cancelled and not is_test and not is_excluded_from_reporting
),

refund_dates as (select refund_date from {{ ref('fct_refunds') }}),

bounds as (
    select
        least(min(o.order_date), coalesce(min(r.refund_date), min(o.order_date)))    as start_date,
        greatest(max(o.order_date), coalesce(max(r.refund_date), max(o.order_date))) as end_date
    from orders o, (select min(refund_date) as refund_date from refund_dates
                    union all select max(refund_date) from refund_dates) r
),

numbers as (
    select row_number() over (order by seq4()) - 1 as n
    from table(generator(rowcount => 2000))
),

spine as (
    select dateadd('day', n.n, b.start_date) as calendar_date
    from numbers n, bounds b
    where dateadd('day', n.n, b.start_date) <= b.end_date
),

daily as (
    select
        order_date,
        count(*)                                        as orders,
        sum(units)                                      as units,
        sum(gross_sales)                                as gross_sales,
        sum(discount_amount)                            as discounts,
        sum(net_sales)                                  as net_sales,
        sum(cogs)                                       as cogs,
        count_if(is_first_order)                        as new_customer_orders,
        count_if(not is_first_order and not is_guest)   as returning_customer_orders,
        count_if(is_guest)                              as guest_orders
    from orders
    group by 1
),

refunds as (
    select refund_date, sum(refund_amount) as refunds_by_refund_date
    from {{ ref('fct_refunds') }}
    group by 1
)

select
    s.calendar_date,
    coalesce(d.orders, 0)                                as orders,
    coalesce(d.units, 0)                                 as units,
    coalesce(d.gross_sales, 0)                           as gross_sales,
    coalesce(d.discounts, 0)                             as discounts,
    coalesce(d.net_sales, 0)                             as net_sales,
    coalesce(r.refunds_by_refund_date, 0)                as refunds,
    coalesce(d.net_sales, 0) - coalesce(r.refunds_by_refund_date, 0) as net_revenue,
    coalesce(d.cogs, 0)                                  as cogs,
    d.net_sales / nullif(d.orders, 0)                    as average_order_value,
    coalesce(d.new_customer_orders, 0)                   as new_customer_orders,
    coalesce(d.returning_customer_orders, 0)             as returning_customer_orders,
    coalesce(d.guest_orders, 0)                          as guest_orders
from spine s
left join daily d   on d.order_date = s.calendar_date
left join refunds r on r.refund_date = s.calendar_date
