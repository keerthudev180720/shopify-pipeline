-- Latest version of each order. Raw is append-only, so an order updated after
-- the first load appears more than once; keep the most recent version.
-- Every orders/order_lines/refunds model builds on this, so dedup happens ONCE.
select
    payload,
    run_id,
    extracted_at
from {{ source('shopify_raw', 'orders') }}
qualify row_number() over (
    partition by payload:id::string
    order by payload:updatedAt::timestamp_tz desc, extracted_at desc
) = 1
