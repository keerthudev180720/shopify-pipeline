-- One row per customer (grain: customer). No PII: IDs and behavior only.
select
    payload:id::string                                   as customer_id,
    {{ to_utc('payload:createdAt') }}                    as created_at,
    {{ to_utc('payload:updatedAt') }}                    as updated_at,
    payload:state::string                                as account_state,
    payload:numberOfOrders::int                          as shopify_order_count,   -- Shopify's own count (used to reconcile)
    payload:amountSpent:amount::number(12, 2)            as shopify_amount_spent,
    payload:tags::array                                  as tags,
    coalesce(array_contains('seeded'::variant, payload:tags::array), false) as is_seeded
from {{ source('shopify_raw', 'customers') }}
qualify row_number() over (
    partition by payload:id::string
    order by payload:updatedAt::timestamp_tz desc, extracted_at desc
) = 1
