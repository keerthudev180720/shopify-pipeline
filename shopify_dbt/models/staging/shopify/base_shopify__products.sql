-- Latest version of each product (same dedup pattern as orders).
select
    payload,
    run_id,
    extracted_at
from {{ source('shopify_raw', 'products') }}
qualify row_number() over (
    partition by payload:id::string
    order by payload:updatedAt::timestamp_tz desc, extracted_at desc
) = 1
