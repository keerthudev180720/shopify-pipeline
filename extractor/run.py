"""Shopify extractor: source system -> raw landing zone.

  orders, products, customers : incremental on updated_at
      window = [last_watermark - 1h overlap, run_start]
      first run (no watermark) = full historical load (backfill)
  inventory                   : full snapshot every run (builds the history
                                Shopify doesn't keep)

Crash safety / idempotency:
  - each entity's file is committed atomically, THEN its watermark advances
  - a crash before that leaves the watermark unchanged, so the next run simply
    re-pulls the same window; duplicates are removed later by MERGE on id
  - the window has a fixed upper bound (run_start), so a run is reproducible

Run from the project root:
  python -m extractor.run                        # all entities
  python -m extractor.run --entities orders      # one entity
  python -m extractor.run --full-refresh         # ignore watermarks, reload all
"""
import argparse, sys, time, uuid
from datetime import datetime, timedelta, timezone
from extractor import queries as Q, state, landing, s3_upload
from seeder.shopify_client import ShopifyClient, GraphQLError

OVERLAP = timedelta(hours=1)

ENTITIES = {
    #  name        query         root field         page  incremental
    "orders":    (Q.ORDERS,    "orders",          15,   True),
    "products":  (Q.PRODUCTS,  "products",        10,   True),
    "customers": (Q.CUSTOMERS, "customers",       100,  True),
    "inventory": (Q.INVENTORY, "productVariants", 25,   False),
}

# nested lists to check for truncation, per entity: (list field, sub-list field or None)
TRUNCATION_CHECKS = {
    "orders": [("lineItems", None), ("refunds", "refundLineItems")],
    "products": [("variants", None)],
    "inventory": [("inventoryItem", "inventoryLevels")],
}


def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def parse(ts):
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def build_search(start, end):
    parts = []
    if start:
        parts.append(f"updated_at:>='{iso(start)}'")
    parts.append(f"updated_at:<='{iso(end)}'")
    return " AND ".join(parts)


def fetch_pages(client, query, root, page_size, search):
    """Cursor pagination. If a page's query cost exceeds Shopify's per-query max,
    halve the page size and retry (adaptive paging)."""
    cursor = None
    while True:
        try:
            data = client.gql(query, {"first": page_size, "after": cursor, "q": search})[root]
        except GraphQLError as e:
            msg = str(e)
            if ("MAX_COST_EXCEEDED" in msg or "max cost" in msg.lower()) and page_size > 1:
                page_size = max(1, page_size // 2)
                print(f"    query too expensive -> page size now {page_size}")
                continue
            raise
        yield data["nodes"]
        if not data["pageInfo"]["hasNextPage"]:
            return
        cursor = data["pageInfo"]["endCursor"]


def truncation_warnings(entity, record):
    """Count nested lists that had more items than we requested."""
    warnings = 0
    for field, sub in TRUNCATION_CHECKS.get(entity, []):
        value = record.get(field)
        if value is None:
            continue
        if sub is None:
            warnings += bool(value.get("pageInfo", {}).get("hasNextPage"))
        else:
            items = value if isinstance(value, list) else [value]
            for it in items:
                warnings += bool((it.get(sub) or {}).get("pageInfo", {}).get("hasNextPage"))
    return warnings


def extract(client, entity, run_id, run_start, full_refresh):
    query, root, page_size, incremental = ENTITIES[entity]
    window_start, mode, search = None, "snapshot", None

    if incremental:
        wm = None if full_refresh else state.get_watermark(entity)
        window_start = parse(wm) - OVERLAP if wm else None
        mode = "incremental" if wm else "full"
        search = build_search(window_start, run_start)

    print(f"== {entity} ({mode}) " + (f"window {iso(window_start) if window_start else 'beginning'} "
                                       f"-> {iso(run_start)}" if incremental else ""))
    writer = landing.RawWriter(entity, run_id, run_start.strftime("%Y-%m-%d"))
    truncated = 0
    try:
        for page in fetch_pages(client, query, root, page_size, search):
            for record in page:
                truncated += truncation_warnings(entity, record)
                writer.write(record)
    except Exception:
        writer.abort()   # no partial files
        raise
    path = writer.commit()

    if s3_upload.enabled():
        s3_upload.upload(path)   # raises on failure -> watermark below does NOT advance
        print(f"   uploaded -> s3://{s3_upload.BUCKET}/{s3_upload.s3_key(path)}")

    if incremental:
        state.set_watermark(entity, iso(run_start))   # ONLY after the file is safely landed (local + S3)

    print(f"   {writer.count} records -> {path}")
    if truncated:
        print(f"   WARNING: {truncated} nested lists were truncated; raise the 'first:' limits in queries.py")
    return {"mode": mode, "records": writer.count, "file": path, "truncated_lists": truncated,
            "window_start": iso(window_start) if window_start else None,
            "window_end": iso(run_start) if incremental else None}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--entities", default=",".join(ENTITIES),
                    help="comma-separated subset of: " + ", ".join(ENTITIES))
    ap.add_argument("--full-refresh", action="store_true")
    args = ap.parse_args()

    entities = [e.strip() for e in args.entities.split(",") if e.strip()]
    unknown = set(entities) - set(ENTITIES)
    if unknown:
        sys.exit(f"Unknown entities: {unknown}")

    run_start = datetime.now(timezone.utc).replace(microsecond=0)
    run_id = run_start.strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:6]  # unique even if two runs start in the same second
    client = ShopifyClient()
    summary = {"run_id": run_id, "started_at": iso(run_start), "entities": {}}
    failed = False
    t0 = time.time()

    for entity in entities:
        try:
            summary["entities"][entity] = {"status": "success",
                                           **extract(client, entity, run_id, run_start, args.full_refresh)}
        except Exception as e:   # keep going with other entities, but record the failure
            failed = True
            summary["entities"][entity] = {"status": "failed", "error": str(e)[:1000]}
            print(f"   FAILED: {str(e)[:300]}")

    summary["status"] = "failed" if failed else "success"
    summary["duration_seconds"] = round(time.time() - t0, 1)
    path = landing.write_run_summary(run_id, summary)
    if s3_upload.enabled():
        try:
            s3_upload.upload(path)
        except Exception as e:
            print(f"   (run summary not uploaded to S3: {e})")
    print(f"\nRun {run_id}: {summary['status']} in {summary['duration_seconds']}s  (summary: {path})")
    sys.exit(1 if failed else 0)   # non-zero exit lets an orchestrator (Airflow) detect failure


if __name__ == "__main__":
    main()