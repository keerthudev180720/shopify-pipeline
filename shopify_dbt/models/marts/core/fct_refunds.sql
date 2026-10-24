-- Grain: one row per refunded line. refund_amount = value of goods returned.
-- refund_date is when the refund happened (NOT the order date) -> used for "refunds this month".
with refund_lines as (select * from {{ ref('stg_shopify__refund_lines') }}),
     refunds      as (select * from {{ ref('stg_shopify__refunds') }}),
     order_lines  as (select * from {{ ref('fct_order_lines') }})

select
    rl.refund_line_id,
    rl.refund_id,
    rl.order_id,
    rl.order_line_id,
    ol.variant_id,
    ol.product_id,
    rl.sku,
    ol.customer_key,
    r.refunded_at,
    {{ local_date('r.refunded_at') }}                      as refund_date,
    r.refund_reason,
    rl.quantity                                            as refunded_quantity,
    rl.restock_type,
    rl.refund_amount,
    ol.processed_at                                        as order_processed_at,
    datediff('day', ol.processed_at, r.refunded_at)        as days_to_refund
from refund_lines rl
join refunds r            on r.refund_id = rl.refund_id
left join order_lines ol  on ol.order_line_id = rl.order_line_id
