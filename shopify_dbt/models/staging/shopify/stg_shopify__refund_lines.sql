-- One row per refunded line (grain: refund line).
-- subtotal = value of goods returned -> this is the refund VALUE we report on.
select
    r.value:id::string || '-' || rli.value:lineItem:id::string as refund_line_id,
    r.value:id::string                                    as refund_id,
    o.payload:id::string                                  as order_id,
    rli.value:lineItem:id::string                         as order_line_id,
    rli.value:lineItem:sku::string                        as sku,
    rli.value:quantity::int                               as quantity,
    rli.value:restockType::string                         as restock_type,
    {{ money('rli.value:subtotalSet') }}                  as refund_amount
from {{ ref('base_shopify__orders') }} o,
     lateral flatten(input => o.payload:refunds) r,
     lateral flatten(input => r.value:refundLineItems:nodes) rli
