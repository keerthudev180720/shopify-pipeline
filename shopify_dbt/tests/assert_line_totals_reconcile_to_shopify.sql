-- Reconciliation: summed line net_sales should equal Shopify's own order total.
-- (Seeded orders have no tax/shipping, so they should match exactly.) Warn, don't fail:
-- real stores add tax/shipping/discounts at order level.
{{ config(severity='warn') }}
select order_id, order_number, net_sales, shopify_total_price
from {{ ref('fct_orders') }}
where abs(coalesce(net_sales, 0) - coalesce(shopify_total_price, 0)) > 0.01
