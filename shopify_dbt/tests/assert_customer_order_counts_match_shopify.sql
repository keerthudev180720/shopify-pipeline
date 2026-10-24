-- Reconciliation: our derived order count per customer vs Shopify's own numberOfOrders.
-- Warn only: Shopify's count may include cancelled/test orders we exclude.
{{ config(severity='warn') }}
select customer_key, order_count, shopify_order_count
from {{ ref('dim_customers') }}
where customer_key != 'GUEST'
  and order_count != coalesce(shopify_order_count, 0)
