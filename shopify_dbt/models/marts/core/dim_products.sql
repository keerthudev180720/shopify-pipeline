-- Grain: one row per product VARIANT (the thing actually sold: e.g. Hoodie / size M).
-- Current attributes only; price history lives in dim_variant_price_history.
with variants as (select * from {{ ref('stg_shopify__variants') }}),
     products as (select * from {{ ref('stg_shopify__products') }})

select
    v.variant_id,
    v.sku,
    v.variant_title,
    v.product_id,
    p.product_title,
    coalesce(p.product_type, 'Uncategorized')                     as category,
    p.vendor,
    p.status                                                      as product_status,
    p.is_gift_card,
    p.is_seeded,
    v.is_tracked,
    (p.status = 'ACTIVE' and not p.is_gift_card)                  as is_sellable,
    v.price                                                       as current_price,
    v.unit_cost,
    case when v.price > 0 and v.unit_cost is not null
         then round((v.price - v.unit_cost) / v.price, 4) end     as gross_margin_pct
from variants v
join products p on p.product_id = v.product_id
