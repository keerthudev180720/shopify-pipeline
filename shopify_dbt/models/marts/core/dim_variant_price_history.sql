-- SCD Type 2: one row per variant per PRICE/COST VERSION, with valid_from / valid_to.
-- Built from ALL raw product extractions (raw is append-only, so every version is kept).
-- A new row starts only when price or cost actually changes, not on every product update.
-- Note: history starts when extraction started; earlier changes are unknowable.
with versions as (
    select distinct
        v.value:id::string                                       as variant_id,
        v.value:sku::string                                      as sku,
        v.value:price::number(12, 2)                             as price,
        v.value:inventoryItem:unitCost:amount::number(12, 2)     as unit_cost,
        {{ to_utc('p.payload:updatedAt') }}                      as source_updated_at
    from {{ source('shopify_raw', 'products') }} p,
         lateral flatten(input => p.payload:variants:nodes) v
),

flagged as (
    select
        *,
        row_number() over (partition by variant_id order by source_updated_at) as version_seq,
        lag(price)     over (partition by variant_id order by source_updated_at) as prev_price,
        lag(unit_cost) over (partition by variant_id order by source_updated_at) as prev_unit_cost
    from versions
),

changes as (
    select * from flagged
    where version_seq = 1
       or price is distinct from prev_price
       or unit_cost is distinct from prev_unit_cost
),

windowed as (
    select
        variant_id || '-' || to_char(source_updated_at, 'YYYYMMDDHH24MISS')       as price_version_id,
        variant_id,
        sku,
        price,
        unit_cost,
        source_updated_at                                                          as valid_from,
        lead(source_updated_at) over (partition by variant_id order by source_updated_at) as valid_to
    from changes
)

select *, (valid_to is null) as is_current
from windowed
