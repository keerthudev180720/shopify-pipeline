-- One row per variant x location x day (grain: daily snapshot).
-- NOT deduped to "latest" like other entities: every day's snapshot is the history.
-- If the extractor ran twice in a day, keep that day's last snapshot.
with levels as (
    select
        extracted_at                                      as snapshot_at,
        extracted_at::date                                as snapshot_date,
        run_id,
        payload:id::string                                as variant_id,
        payload:sku::string                               as sku,
        payload:product:id::string                        as product_id,
        payload:inventoryItem:id::string                  as inventory_item_id,
        payload:inventoryItem:tracked::boolean            as is_tracked,
        lvl.value:location:id::string                     as location_id,
        lvl.value:location:name::string                   as location_name,
        lvl.value:quantities                              as quantities
    from {{ source('shopify_raw', 'inventory') }},
         lateral flatten(input => payload:inventoryItem:inventoryLevels:nodes) lvl
),

pivoted as (
    select
        snapshot_at, snapshot_date, run_id, variant_id, sku, product_id,
        inventory_item_id, is_tracked, location_id, location_name,
        max(case when q.value:name::string = 'available' then q.value:quantity::int end) as available_qty,
        max(case when q.value:name::string = 'on_hand'   then q.value:quantity::int end) as on_hand_qty,
        max(case when q.value:name::string = 'committed' then q.value:quantity::int end) as committed_qty
    from levels,
         lateral flatten(input => quantities) q
    group by all
)

select
    variant_id || '-' || location_id || '-' || to_char(snapshot_date, 'YYYY-MM-DD') as inventory_snapshot_id,
    *
from pivoted
qualify row_number() over (
    partition by variant_id, location_id, snapshot_date
    order by snapshot_at desc
) = 1
