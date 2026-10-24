-- One row per refund (grain: refund). Refunds are nested inside orders.
select
    r.value:id::string                                    as refund_id,
    o.payload:id::string                                  as order_id,
    {{ to_utc('r.value:processedAt') }}                   as refunded_at,    -- business date (backdated)
    {{ to_utc('r.value:createdAt') }}                     as created_at,
    r.value:note::string                                  as note,
    nullif(trim(regexp_substr(r.value:note::string, 'Reason: (.*)', 1, 1, 'e')), '') as refund_reason,
    {{ money('r.value:totalRefundedSet') }}               as refunded_money  -- $0 for seeded orders
from {{ ref('base_shopify__orders') }} o,
     lateral flatten(input => o.payload:refunds) r
