-- One row per order (grain: order). Business date = processed_at.
select
    payload:id::string                                   as order_id,
    payload:name::string                                 as order_number,

    {{ to_utc('payload:processedAt') }}                  as processed_at,   -- business date (backdated)
    {{ to_utc('payload:createdAt') }}                    as created_at,     -- when the record was inserted
    {{ to_utc('payload:updatedAt') }}                    as updated_at,     -- last change (incremental key)
    {{ to_utc('payload:cancelledAt') }}                  as cancelled_at,
    {{ to_utc('payload:closedAt') }}                     as closed_at,

    payload:displayFinancialStatus::string               as financial_status,
    payload:displayFulfillmentStatus::string             as fulfillment_status,
    payload:currencyCode::string                         as currency,

    payload:customer:id::string                          as customer_id,     -- null = guest checkout
    (payload:customer:id is null)                        as is_guest,

    {{ money('payload:subtotalPriceSet') }}              as subtotal_price,
    {{ money('payload:totalDiscountsSet') }}             as total_discounts,
    {{ money('payload:totalTaxSet') }}                   as total_tax,
    {{ money('payload:totalPriceSet') }}                 as total_price,
    {{ money('payload:totalRefundedSet') }}              as total_refunded_money,  -- $0 for seeded orders (no payment txns)

    array_size(payload:lineItems:nodes)                  as line_item_count,
    payload:tags::array                                  as tags,
    coalesce(array_contains('seeded'::variant, payload:tags::array), false) as is_seeded,
    coalesce(payload:test::boolean, false)               as is_test,

    run_id                                               as _run_id,
    extracted_at                                         as _extracted_at
from {{ ref('base_shopify__orders') }}
