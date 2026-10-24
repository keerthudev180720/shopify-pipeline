-- One row per product (grain: product).
select
    payload:id::string                                   as product_id,
    payload:title::string                                as product_title,
    payload:handle::string                               as handle,
    nullif(payload:productType::string, '')              as product_type,
    payload:vendor::string                               as vendor,
    payload:status::string                               as status,          -- ACTIVE / ARCHIVED / DRAFT
    coalesce(payload:isGiftCard::boolean, false)         as is_gift_card,
    payload:tags::array                                  as tags,
    coalesce(array_contains('seeded'::variant, payload:tags::array), false) as is_seeded,
    {{ to_utc('payload:createdAt') }}                    as created_at,
    {{ to_utc('payload:updatedAt') }}                    as updated_at
from {{ ref('base_shopify__products') }}
