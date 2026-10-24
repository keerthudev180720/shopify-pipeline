-- Grain: one row per variant per snapshot day (summed across locations).
-- days_on_hand = on-hand units / average daily units sold over the trailing 28 days.
-- History exists only from the first extraction day onward (Shopify keeps none).
with inventory as (
    select
        snapshot_date,
        variant_id,
        sku,
        product_id,
        boolor_agg(is_tracked)   as is_tracked,
        sum(available_qty)       as available_qty,
        sum(on_hand_qty)         as on_hand_qty,
        sum(committed_qty)       as committed_qty
    from {{ ref('stg_shopify__inventory_levels') }}
    group by 1, 2, 3, 4
),

sales_daily as (
    select variant_id, order_date, sum(quantity) as units_sold
    from {{ ref('fct_order_lines') }}
    where not is_cancelled and not is_test and not is_excluded_from_reporting
    group by 1, 2
),

with_sales as (
    select
        i.snapshot_date, i.variant_id, i.sku, i.product_id, i.is_tracked,
        i.available_qty, i.on_hand_qty, i.committed_qty,
        coalesce(sum(s.units_sold), 0)                     as units_sold_28d
    from inventory i
    left join sales_daily s
           on s.variant_id = i.variant_id
          and s.order_date between dateadd('day', -27, i.snapshot_date) and i.snapshot_date
    group by 1, 2, 3, 4, 5, 6, 7, 8
)

select
    variant_id || '-' || to_char(snapshot_date, 'YYYY-MM-DD')  as inventory_day_id,
    *,
    round(units_sold_28d / 28.0, 3)                             as avg_daily_units_28d,
    case when units_sold_28d > 0
         then round(on_hand_qty / (units_sold_28d / 28.0), 1) end as days_on_hand,
    (is_tracked and available_qty <= 0)                         as is_stocked_out
from with_sales
