# Metrics Specification

Every number on the dashboard is defined here: formula, source model, and what is included or excluded. If a dashboard number and this document disagree, the document is the contract and the dashboard is the bug.

## Global rules

**Reporting scope.** KPIs include only completed business activity. An order is excluded when any of these is true:

| Flag (in `fct_orders` / `fct_order_lines`) | Meaning |
|---|---|
| `is_cancelled` | Order was cancelled |
| `is_test` | Shopify marked it as a test order |
| `is_excluded_from_reporting` | Internal/test order (manual admin orders and the backdating test; 11 orders) |

Excluded orders are never deleted. They stay in the fact tables, flagged, so the source data remains complete and reconcilable.

**Dates.** Business dates (`order_date`, `refund_date`, `calendar_date`) are in the store's local time zone (`America/Los_Angeles`, set by the `store_timezone` dbt var). All timestamps (`processed_at`, `refunded_at`) are stored in UTC. Example: an order at 2025-10-01 02:39 UTC is reported on 2025-09-30.

**Business date vs. system dates.** Sales are dated by `processed_at` (when the sale happened). `created_at` and `updated_at` are system timestamps and are never used for reporting.

**Currency.** USD. Amounts are `NUMBER(12,2)`, never floats.

---

## Sales

| Metric | Formula | Source | Notes |
|---|---|---|---|
| **Gross sales** | Σ (quantity × unit price at time of sale) | `fct_order_lines.gross_sales` | Uses the price on the order line, never the current product price |
| **Discounts** | Σ (gross sales − discounted line total) | `fct_order_lines.discount_amount` | Line-level discounts only |
| **Net sales** | Gross sales − discounts | `fct_order_lines.net_sales` | Excludes tax and shipping |
| **Refunds (finance view)** | Σ refund amount, dated by **refund date** | `agg_daily_sales.refunds` (from `fct_refunds`) | "Money returned this month" |
| **Refunds (order view)** | Σ refund amount, attributed to the **original order date** | `fct_orders.refunded_amount` | "How much of September's sales came back" |
| **Net revenue (daily KPI)** | Net sales − refunds (finance view) | `agg_daily_sales.net_revenue` | Used on the executive page |
| **Net revenue (order level)** | Net sales − refunds (order view) | `fct_orders.net_revenue`, `fct_order_lines.net_revenue` | Used for product and cohort analysis |
| **COGS** | Σ (quantity × unit cost) | `fct_order_lines.cogs` | Uses **current** unit cost (see limitations) |
| **Gross margin %** | (Net sales − COGS) ÷ net sales | Computed from `fct_order_lines` | Directional only, because COGS uses current cost |

**Why two refund views:** a refund issued in October for a September order lowers October's cash (finance view) but September's sales quality (order view). Each chart states which one it uses.

**Refund value source:** refund value comes from refunded line items (`refundLineItems.subtotal`), because seeded orders have no payment transactions and Shopify records $0 of money refunded. In a store with real payments, refund transactions would be reconciled against this value.

---

## Orders

| Metric | Formula | Source |
|---|---|---|
| **Orders** | Count of orders in scope | `agg_daily_sales.orders` / `fct_orders` |
| **Units sold** | Σ quantity | `fct_orders.units` |
| **Average order value (AOV)** | Net sales ÷ orders | `agg_daily_sales.average_order_value` |
| **Units per order** | Units ÷ orders | Computed from `fct_orders` |

AOV is always net sales ÷ orders. Recompute it from totals when aggregating over a period; never average the daily AOVs, which would weight a slow day the same as a busy one.

---

## Customers

| Metric | Formula | Source | Notes |
|---|---|---|---|
| **New customer orders** | Orders where `customer_order_sequence = 1` | `agg_daily_sales.new_customer_orders` | A customer's first order |
| **Returning customer orders** | Orders where sequence > 1, excluding guests | `agg_daily_sales.returning_customer_orders` | |
| **Guest order share** | Guest orders ÷ orders | `agg_daily_sales.guest_orders` | Guests can't be tracked across orders |
| **Repeat purchase rate** | Customers with ≥ 2 orders ÷ customers with ≥ 1 order | `dim_customers.order_count` | Excludes `no_purchase` customers and the GUEST row |
| **Customer segment** | `vip` ≥ 10 orders; `repeat` 2–9; `one_time` 1; `no_purchase` 0; `guest` | `dim_customers.customer_segment` | Thresholds are dbt vars (`vip_min_orders`, `repeat_min_orders`) |
| **Acquisition month** | Month of the customer's first order | `dim_customers.acquisition_month` | Not Shopify's `createdAt`, which is only when the record was made |
| **Customer lifetime net revenue** | Σ net revenue across the customer's orders | `dim_customers.lifetime_net_revenue` | |

Segments are derived from order behavior. They were validated against the seeder's hidden labels: matching within a few percent, with differences traced to orders skipped during stockouts.

Example, repeat purchase rate:
```sql
SELECT COUNT_IF(order_count >= 2) / NULLIF(COUNT_IF(order_count >= 1), 0) AS repeat_purchase_rate
FROM SHOPIFY.MARTS.DIM_CUSTOMERS
WHERE customer_key != 'GUEST';
```

---

## Returns

| Metric | Formula | Source | Notes |
|---|---|---|---|
| **Return rate (units)** | Refunded units ÷ units sold, for orders in the period | `fct_order_lines` | By **order date** (order view) |
| **Refund rate (value)** | Refunded amount ÷ net sales, for orders in the period | `fct_order_lines` | By order date |
| **Days to refund** | Refund timestamp − order timestamp, in days | `fct_refunds.days_to_refund` | |
| **Refunds by reason** | Count or value grouped by `refund_reason` | `fct_refunds` | Parsed from the refund note |

Example, return rate by product:
```sql
SELECT p.product_title,
       SUM(l.refunded_quantity) / NULLIF(SUM(l.quantity), 0) AS return_rate
FROM SHOPIFY.MARTS.FCT_ORDER_LINES l
JOIN SHOPIFY.MARTS.DIM_PRODUCTS p USING (variant_id)
WHERE NOT l.is_cancelled AND NOT l.is_test AND NOT l.is_excluded_from_reporting
GROUP BY 1
ORDER BY 2 DESC;
```

---

## Inventory

| Metric | Formula | Source | Notes |
|---|---|---|---|
| **On-hand / available units** | Σ across locations, per variant per day | `fct_inventory_daily` | Daily snapshot |
| **Stocked out** | Tracked variant with available ≤ 0 | `fct_inventory_daily.is_stocked_out` | |
| **Average daily units (28d)** | Units sold in the trailing 28 days ÷ 28 | `fct_inventory_daily.avg_daily_units_28d` | Excludes out-of-scope orders |
| **Days on hand** | On-hand units ÷ average daily units (28d) | `fct_inventory_daily.days_on_hand` | Null when nothing sold in 28 days |

---

## Data quality and reconciliation

These checks run on every `dbt build`. A failing test stops downstream models from building.

| Check | What it proves | Severity |
|---|---|---|
| Unique / not-null keys on every model | Each table's grain holds | Error |
| Relationship tests (lines → orders → customers, refunds → lines) | No orphaned rows from broken joins | Error |
| `assert_fct_orders_match_staging` | No orders lost between staging and marts | Error |
| `assert_refunds_do_not_exceed_sales` | No line refunds more than it sold | Error |
| `assert_customer_order_counts_match_shopify` | Derived order counts match Shopify's own `numberOfOrders` | Warn |
| `assert_line_totals_reconcile_to_shopify` | Line net sales match Shopify's order totals | Warn: currently 6 known differences from manual orders that include tax and shipping |
| Source freshness | Raw data loaded within 26h (warn) / 50h (error) | Warn / Error |

The extraction itself was also reconciled: the full load extracted 2,053 orders against Shopify's own count of 2,053.

---

## Known limitations

1. **Synthetic data.** Orders, customers, and refunds were generated by the seeder through the real Shopify API. The pipeline, API behavior, and failure handling are real; the business activity is simulated.
2. **COGS uses current unit cost.** Shopify exposes only the current cost, so historical margins assume today's costs.
3. **Inventory history starts at the first extraction.** Shopify keeps no inventory history, so days-on-hand trends begin on the first snapshot day. The backdated year has sales but no stock levels.
4. **Days on hand near the data's end.** Seeded sales end on 2026-09-28, so later snapshots see fewer trailing sales and higher days on hand.
5. **Customer stats include internal orders.** `dim_customers` counts all completed non-test orders, including the 10 manual admin orders, so it reconciles with Shopify's own counts. This affects 3 legacy customers only.
6. **Price history starts at the first extraction.** `dim_variant_price_history` can only record changes seen since extraction began.