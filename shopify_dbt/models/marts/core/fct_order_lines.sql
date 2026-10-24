-- Grain: one row per order line item. The core fact table.
-- Revenue uses the price AT TIME OF SALE (from the order line), never the current price.
with lines    as (select * from {{ ref('stg_shopify__order_lines') }}),
     orders   as (select * from {{ ref('stg_shopify__orders') }}),
     products as (select variant_id, unit_cost from {{ ref('dim_products') }}),
     refunds  as (
        select
            order_line_id,
            sum(quantity)       as refunded_quantity,
            sum(refund_amount)  as refunded_amount
        from {{ ref('stg_shopify__refund_lines') }}
        group by 1
     )

select
    l.order_line_id,
    l.order_id,
    o.order_number,
    coalesce(o.customer_id, 'GUEST')                              as customer_key,
    o.is_guest,
    l.variant_id,
    l.product_id,
    l.sku,

    o.processed_at,
    {{ local_date('o.processed_at') }}                            as order_date,
    o.financial_status,
    (o.cancelled_at is not null)                                  as is_cancelled,
    o.is_test,
    o.is_seeded,
    (not o.is_seeded or o.is_test)                                as is_excluded_from_reporting,  -- internal/test orders

    l.quantity,
    l.unit_price,
    l.gross_line_amount                                           as gross_sales,
    l.gross_line_amount - coalesce(l.discounted_line_total, l.gross_line_amount) as discount_amount,
    coalesce(l.discounted_line_total, l.gross_line_amount)        as net_sales,

    p.unit_cost,                                                  -- CURRENT cost (cost history not available for past sales)
    l.quantity * p.unit_cost                                      as cogs,

    coalesce(r.refunded_quantity, 0)                              as refunded_quantity,
    coalesce(r.refunded_amount, 0)                                as refunded_amount,
    coalesce(l.discounted_line_total, l.gross_line_amount)
        - coalesce(r.refunded_amount, 0)                          as net_revenue,
    (r.order_line_id is not null)                                 as is_refunded
from lines l
join orders o        on o.order_id = l.order_id
left join products p on p.variant_id = l.variant_id
left join refunds r  on r.order_line_id = l.order_line_id
