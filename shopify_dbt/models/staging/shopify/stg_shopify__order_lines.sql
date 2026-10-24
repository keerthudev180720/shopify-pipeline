-- One row per line item (grain: order line). Flattens the nested lineItems list.
select
    li.value:id::string                                   as order_line_id,
    o.payload:id::string                                  as order_id,
    li.value:variant:id::string                           as variant_id,
    li.value:product:id::string                           as product_id,
    li.value:sku::string                                  as sku,
    li.value:name::string                                 as line_name,
    li.value:quantity::int                                as quantity,
    {{ money('li.value:originalUnitPriceSet') }}          as unit_price,
    {{ money('li.value:discountedTotalSet') }}            as discounted_line_total,
    li.value:quantity::int
        * {{ money('li.value:originalUnitPriceSet') }}    as gross_line_amount
from {{ ref('base_shopify__orders') }} o,
     lateral flatten(input => o.payload:lineItems:nodes) li
