-- One row per variant (grain: variant), CURRENT values only.
-- Price history (SCD2) is built later in marts from ALL raw versions.
select
    v.value:id::string                                    as variant_id,
    p.payload:id::string                                  as product_id,
    v.value:sku::string                                   as sku,
    v.value:title::string                                 as variant_title,
    v.value:price::number(12, 2)                          as price,
    v.value:compareAtPrice::number(12, 2)                 as compare_at_price,
    v.value:inventoryItem:unitCost:amount::number(12, 2)  as unit_cost,
    v.value:inventoryItem:id::string                      as inventory_item_id,
    v.value:inventoryItem:tracked::boolean                as is_tracked,
    {{ to_utc('v.value:createdAt') }}                     as created_at,
    {{ to_utc('v.value:updatedAt') }}                     as updated_at
from {{ ref('base_shopify__products') }} p,
     lateral flatten(input => p.payload:variants:nodes) v
